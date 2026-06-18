#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_daily.py — AI 뉴스레터 자동화 플랫폼 일일 수집기

수집 대상:
  - 뉴스/논문   : source-registry.json (RSS 우선, 실패 시 건너뜀)
  - AI 구루 발언 : people-registry.json (RSS/공개 글, X 직접 크롤링 없음)
  - 유튜브 브리프: youtube-registry.json (YouTube RSS, channelId 없으면 handle로 해석)

설계 원칙:
  - 한 소스가 실패해도 전체 수집은 멈추지 않는다 (소스 단위 try/except 격리).
  - 카테고리/태그/검색 등 목록 페이지 URL은 제외하고 기사 상세만 유지.
  - 중복 제거 + 출처별 최대 노출 개수 제한.
  - LLM 없이도 fallback 요약으로 완성된 data/latest.json 을 생성한다.
  - summarize_with_llm.py 가 존재하고 API 키가 있으면 자동으로 고품질 요약으로 덮어쓴다.

실행:
  python scrape_daily.py
"""

import os
import re
import sys
import json
import time
import html
import datetime
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("[FATAL] requests 가 필요합니다. `pip install -r requirements.txt` 를 먼저 실행하세요.")
    sys.exit(1)

try:
    import feedparser
except ImportError:
    print("[FATAL] feedparser 가 필요합니다. `pip install -r requirements.txt` 를 먼저 실행하세요.")
    sys.exit(1)

# TLS 검증을 OS 인증서 저장소로 위임 (사내/프록시 환경의 self-signed CA 대응).
# 설치돼 있지 않으면 기본 certifi 번들을 사용한다.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# 선택적 의존성 (없어도 동작)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from bs4 import BeautifulSoup
    HAVE_BS4 = True
except Exception:
    HAVE_BS4 = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAVE_TRANSCRIPT = True
except Exception:
    HAVE_TRANSCRIPT = False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DAILY_DIR = os.path.join(DATA_DIR, "daily")
KST = datetime.timezone(datetime.timedelta(hours=9))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ai-newsletter-bot/1.0"
)


# --------------------------------------------------------------------------- #
# 유틸리티
# --------------------------------------------------------------------------- #
def log(level, msg):
    print(f"[{level}] {msg}", flush=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def http_get(url, timeout=15, retry=1):
    """resilient GET. 실패 시 None 반환."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en,ko;q=0.8"}
    last_err = None
    for attempt in range(retry + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last_err = f"HTTP {resp.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(0.6)
    log("WARN", f"GET 실패 ({last_err}): {url}")
    return None


def clean_text(text, limit=600):
    if not text:
        return ""
    text = html.unescape(text)
    if HAVE_BS4:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    else:
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def normalize_url(url):
    if not url:
        return ""
    url = url.strip()
    url = re.sub(r"#.*$", "", url)  # 프래그먼트만 제거 (쿼리는 식별자일 수 있어 보존: ?v=, ?id= 등)
    return url.rstrip("/").lower()


def to_iso(entry):
    """feedparser entry → ISO 날짜 문자열 (없으면 빈 문자열)."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.datetime(*t[:6], tzinfo=datetime.timezone.utc).isoformat()
            except Exception:  # noqa: BLE001
                continue
    return ""


# --------------------------------------------------------------------------- #
# URL 품질 필터
# --------------------------------------------------------------------------- #
def is_excluded_url(url, patterns):
    """카테고리/태그/검색 등 목록 페이지는 제외."""
    if not url:
        return True
    low = url.lower()
    path = urlparse(low).path
    for pat in patterns:
        if pat in low:
            return True
    # 상세 기사로 보기 어려운 매우 얕은 경로 제외 (도메인 루트 등)
    if path in ("", "/"):
        return True
    return False


# --------------------------------------------------------------------------- #
# 수집: 뉴스 / 논문 (RSS)
# --------------------------------------------------------------------------- #
def collect_feed_source(src, defaults, exclusion_patterns, kind):
    """단일 RSS 소스 수집. 실패해도 예외를 밖으로 던지지 않음."""
    items = []
    rss = (src.get("rss") or "").strip()
    if not rss:
        log("SKIP", f"{src['name']}: RSS 미등록 (homepage 스크래핑은 추후 단계)")
        return items

    max_items = src.get("maxItems", defaults.get("maxItems", 5))
    resp = http_get(rss, timeout=defaults.get("requestTimeoutSec", 15),
                    retry=defaults.get("retry", 1))
    if resp is None:
        return items

    feed = feedparser.parse(resp.content)
    if not feed.entries:
        log("WARN", f"{src['name']}: 항목 없음")
        return items

    for entry in feed.entries:
        link = entry.get("link", "")
        if kind == "news" and is_excluded_url(link, exclusion_patterns):
            continue
        title = clean_text(entry.get("title", ""), limit=300)
        if not title or not link:
            continue
        desc = clean_text(
            entry.get("summary", "") or entry.get("description", ""), limit=700
        )
        item = {
            "id": f"{src['id']}::{normalize_url(link)}",
            "sourceId": src["id"],
            "sourceName": src["name"],
            "lang": src.get("language", "en"),
            "trust": src.get("trust", "medium"),
            "title": title,
            "url": link,
            "description": desc,
            "publishedAt": to_iso(entry),
        }
        if kind == "paper":
            authors = entry.get("authors") or []
            item["authors"] = [a.get("name", "") for a in authors if a.get("name")]
        items.append(item)
        if len(items) >= max_items:
            break

    log("OK", f"{src['name']}: {len(items)}건")
    return items


def collect_news_and_papers(registry):
    defaults = registry.get("defaults", {})
    patterns = registry.get("urlExclusionPatterns", [])
    articles, papers = [], []
    used_sources = set()

    for src in registry.get("newsSources", []):
        try:
            got = collect_feed_source(src, defaults, patterns, "news")
            if got:
                used_sources.add(src["id"])
            articles.extend(got)
        except Exception as e:  # noqa: BLE001
            log("ERROR", f"{src.get('name')} 수집 중 예외: {e}")

    for src in registry.get("paperSources", []):
        try:
            got = collect_feed_source(src, defaults, patterns, "paper")
            if got:
                used_sources.add(src["id"])
            papers.extend(got)
        except Exception as e:  # noqa: BLE001
            log("ERROR", f"{src.get('name')} 수집 중 예외: {e}")

    return articles, papers, used_sources


# --------------------------------------------------------------------------- #
# 수집: AI 구루 발언
# --------------------------------------------------------------------------- #
def collect_gurus(registry):
    defaults = registry.get("defaults", {})
    mentions = []
    for person in registry.get("people", []):
        per_max = defaults.get("maxItems", 3)
        got = 0
        for source in person.get("sources", []):
            rss = (source.get("rss") or "").strip()
            if not rss:
                continue  # 출처 링크 명확한 RSS만 수집 (X 직접 크롤링 없음)
            try:
                resp = http_get(rss, timeout=defaults.get("requestTimeoutSec", 15),
                                retry=defaults.get("retry", 1))
                if resp is None:
                    continue
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    link = entry.get("link", "")
                    title = clean_text(entry.get("title", ""), limit=300)
                    if not title or not link:
                        continue
                    body = clean_text(
                        entry.get("summary", "") or entry.get("description", ""),
                        limit=900,
                    )
                    mentions.append({
                        "id": f"{person['id']}::{normalize_url(link)}",
                        "personId": person["id"],
                        "name": person["name"],
                        "title": person.get("title", ""),
                        "org": person.get("org", ""),
                        "sourceType": source.get("type", "web"),
                        "quoteTitle": title,
                        "quoteText": body,
                        "url": link,
                        "publishedAt": to_iso(entry),
                        "lang": "en",
                    })
                    got += 1
                    if got >= per_max:
                        break
            except Exception as e:  # noqa: BLE001
                log("ERROR", f"{person['name']} 수집 중 예외: {e}")
            if got >= per_max:
                break
        if got:
            log("OK", f"구루 {person['name']}: {got}건")
    return mentions


# --------------------------------------------------------------------------- #
# 수집: 유튜브
# --------------------------------------------------------------------------- #
CHANNEL_ID_RE = re.compile(r'"(?:externalId|channelId)":"(UC[\w-]{22})"')
CANONICAL_RE = re.compile(r'channel/(UC[\w-]{22})')


def resolve_channel_id(channel_url):
    """channelId 가 비어 있을 때 채널 페이지 HTML에서 해석."""
    resp = http_get(channel_url, timeout=15, retry=1)
    if resp is None:
        return ""
    m = CHANNEL_ID_RE.search(resp.text) or CANONICAL_RE.search(resp.text)
    return m.group(1) if m else ""


def fetch_transcript(video_id):
    if not HAVE_TRANSCRIPT:
        return ""
    try:
        chunks = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "ko"]
        )
        text = " ".join(c["text"] for c in chunks)
        return clean_text(text, limit=2500)
    except Exception:  # noqa: BLE001  자막 없거나 비활성 → 조용히 생략
        return ""


def extract_video_id(url):
    m = re.search(r"v=([\w-]{11})", url) or re.search(r"youtu\.be/([\w-]{11})", url)
    return m.group(1) if m else ""


def collect_youtube(registry):
    defaults = registry.get("defaults", {})
    per_max = defaults.get("maxItemsPerChannel", 2)
    template = registry.get("feedUrlTemplate",
                            "https://www.youtube.com/feeds/videos.xml?channel_id={channelId}")
    briefs = []

    for ch in registry.get("channels", []):
        try:
            feed_url = (ch.get("feed") or "").strip()
            channel_id = (ch.get("channelId") or "").strip()
            if not feed_url:
                if not channel_id and ch.get("channelUrl"):
                    channel_id = resolve_channel_id(ch["channelUrl"])
                    if channel_id:
                        log("INFO", f"{ch['name']}: channelId 해석됨 {channel_id}")
                if channel_id:
                    feed_url = template.format(channelId=channel_id)
            if not feed_url:
                log("SKIP", f"{ch['name']}: feed 해석 실패")
                continue

            resp = http_get(feed_url, timeout=defaults.get("requestTimeoutSec", 15),
                            retry=defaults.get("retry", 1))
            if resp is None:
                continue
            feed = feedparser.parse(resp.content)
            got = 0
            for entry in feed.entries:
                link = entry.get("link", "")
                title = clean_text(entry.get("title", ""), limit=300)
                if not title or not link:
                    continue
                desc = clean_text(
                    entry.get("summary", "")
                    or (entry.get("media_description", "") if entry.get("media_description") else ""),
                    limit=900,
                )
                vid = entry.get("yt_videoid", "") or extract_video_id(link)
                transcript = fetch_transcript(vid) if vid else ""
                briefs.append({
                    "id": f"{ch['id']}::{vid or normalize_url(link)}",
                    "channelId": ch["id"],
                    "channelName": ch["name"],
                    "videoTitle": title,
                    "url": link,
                    "description": desc,
                    "transcriptExcerpt": transcript,
                    "hasTranscript": bool(transcript),
                    "baselineTier": ch.get("baselineTier", "medium"),
                    "publishedAt": to_iso(entry),
                    "lang": "en",
                })
                got += 1
                if got >= per_max:
                    break
            if got:
                log("OK", f"유튜브 {ch['name']}: {got}건")
        except Exception as e:  # noqa: BLE001
            log("ERROR", f"{ch.get('name')} 수집 중 예외: {e}")
    return briefs


# --------------------------------------------------------------------------- #
# 중복 제거
# --------------------------------------------------------------------------- #
def dedupe(items, url_key="url", title_key="title"):
    seen_url, seen_title = set(), set()
    out = []
    for it in items:
        u = normalize_url(it.get(url_key, ""))
        t = re.sub(r"\s+", " ", (it.get(title_key, "") or "")).strip().lower()
        if u and u in seen_url:
            continue
        if t and t in seen_title:
            continue
        if u:
            seen_url.add(u)
        if t:
            seen_title.add(t)
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
# 품질 필터링 (스펙 9절)
# --------------------------------------------------------------------------- #
# 과장/낚시성 키워드 (영문 + 국문)
HYPE_WORDS = [
    "shocking", "insane", "unbelievable", "mind-blowing", "mind blowing",
    "you won't believe", "you wont believe", "this changes everything",
    "the end of", "is dead", "agi is here", "terrifying", "scary", "breaks",
    "destroys", "war", "panic", "secret", "exposed", "nobody is talking",
    "충격", "소름", "경악", "미쳤", "역대급", "초유의", "발칵", "난리", "끝났다",
]
# 광고/협찬 신호
AD_WORDS = [
    "sponsor", "sponsored", "use code", "promo code", "discount code",
    "affiliate", "#ad", "paid promotion", "협찬", "광고", "프로모션", "할인코드",
]


def detect_hype(title, description=""):
    """유튜브 제목/설명의 과장·광고성 신호 감지. (hype, ad) 튜플 반환."""
    text = f"{title} {description}".lower()
    hype = any(w in text for w in HYPE_WORDS)
    # 과도한 느낌표/물음표, 전체 대문자 비율도 과장 신호
    if title.count("!") >= 2 or title.count("?") >= 2:
        hype = True
    letters = [c for c in title if c.isalpha() and c.isascii()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6 and len(letters) > 8:
        hype = True
    ad = any(w in text for w in AD_WORDS)
    return hype, ad


def cap_per_source(items, key, cap):
    """출처별 최대 노출 개수 제한 (수집 순서 유지)."""
    counts = {}
    out = []
    for it in items:
        k = it.get(key, "")
        counts[k] = counts.get(k, 0) + 1
        if counts[k] <= cap:
            out.append(it)
    return out


def apply_quality_filters(payload, source_defaults, youtube_defaults):
    """중복 제거 이후 단계: URL 없는 항목 제거, 출처 상한, 유튜브 과장/광고 플래그."""
    cap = source_defaults.get("maxItems", 5)

    # 기사/논문: URL·제목 필수 + 출처별 상한
    payload["articles"] = cap_per_source(
        [a for a in payload["articles"] if a.get("url") and a.get("title")],
        "sourceName", cap,
    )
    payload["papers"] = [p for p in payload["papers"] if p.get("url") and p.get("title")]

    # 구루: 출처 링크 없는 발언 제외 (출처 불명확 차단)
    before = len(payload["guruMentions"])
    payload["guruMentions"] = [
        g for g in payload["guruMentions"] if g.get("url") and g.get("quoteTitle")
    ]
    dropped_guru = before - len(payload["guruMentions"])

    # 유튜브: 채널별 상한 + 과장/광고 플래그
    ycap = youtube_defaults.get("maxItemsPerChannel", 2)
    payload["youtubeBriefs"] = cap_per_source(
        [y for y in payload["youtubeBriefs"] if y.get("url") and y.get("videoTitle")],
        "channelName", ycap,
    )
    hype_count = 0
    for y in payload["youtubeBriefs"]:
        hype, ad = detect_hype(y.get("videoTitle", ""), y.get("description", ""))
        y["hypeFlag"] = bool(hype or ad)
        if y["hypeFlag"]:
            hype_count += 1
            y["needsVerification"] = True  # fallback에서도 경고 표시
            # 공식/고신뢰 채널이 아니면 신뢰도 baseline 하향
            if y.get("baselineTier") == "medium":
                y["baselineTier"] = "low"

    if dropped_guru:
        log("FILTER", f"출처 불명확 구루 발언 {dropped_guru}건 제외")
    if hype_count:
        log("FILTER", f"유튜브 과장/광고성 의심 {hype_count}건 플래그")
    return payload


# --------------------------------------------------------------------------- #
# Fallback 요약 (LLM 없이도 화면이 보이도록)
# --------------------------------------------------------------------------- #
def fallback_enrich(payload):
    """LLM 미사용 시 원문 기반 최소 카드 필드 채움. llm=False 로 표시."""
    for a in payload["articles"]:
        a.setdefault("titleKo", a["title"])
        a.setdefault("summaryKo", a["description"])
        a.setdefault("insights", [])
        a.setdefault("keyPoints", [])
        a.setdefault("soWhat", "")
        a.setdefault("execLine", "")
        a["llm"] = False
    for g in payload["guruMentions"]:
        g.setdefault("summaryKo", g.get("quoteText", ""))
        g.setdefault("meaning", "")
        g.setdefault("businessImplication", "")
        g.setdefault("caution", "")
        g["llm"] = False
    for y in payload["youtubeBriefs"]:
        y.setdefault("summaryKo", y.get("description", ""))
        y.setdefault("keyPoints", [])
        y.setdefault("implication", "")
        y.setdefault("trust", y.get("baselineTier", "medium"))
        y.setdefault("needsVerification", False)
        y["llm"] = False
    for p in payload["papers"]:
        p.setdefault("titleKo", p["title"])
        p.setdefault("topic", "")
        p.setdefault("contribution", p["description"])
        p.setdefault("applicability", "")
        p.setdefault("marketingAngle", "")
        p.setdefault("difficulty", "")
        p["llm"] = False

    payload["dailyInsight"] = {
        "headline": "오늘 수집된 AI 동향 요약",
        "body": (
            f"오늘 뉴스 {len(payload['articles'])}건, 구루 발언 "
            f"{len(payload['guruMentions'])}건, 유튜브 {len(payload['youtubeBriefs'])}건, "
            f"논문 {len(payload['papers'])}건을 수집했습니다. "
            "LLM 요약을 활성화하면(.env에 API 키 입력) 전문 에디터 톤의 한국어 인사이트가 생성됩니다."
        ),
        "connections": [],
        "watchNext": [],
        "llm": False,
    }
    top = payload["articles"][:5]
    payload["reportSummary"] = {
        "topTrends": [
            {"title": a["title"], "evidenceUrl": a["url"], "soWhat": "", "quote": ""}
            for a in top
        ],
        "actions": [],
        "risks": [],
        "llm": False,
    }
    return payload


# --------------------------------------------------------------------------- #
# 메인
# --------------------------------------------------------------------------- #
def main():
    today = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    now_iso = datetime.datetime.now(KST).isoformat(timespec="seconds")
    log("INFO", f"수집 시작: {today}")

    source_reg = load_json(os.path.join(BASE_DIR, "source-registry.json"))
    people_reg = load_json(os.path.join(BASE_DIR, "people-registry.json"))
    youtube_reg = load_json(os.path.join(BASE_DIR, "youtube-registry.json"))

    articles, papers, used_sources = collect_news_and_papers(source_reg)
    gurus = collect_gurus(people_reg)
    youtube = collect_youtube(youtube_reg)

    # 중복 제거
    articles = dedupe(articles)
    papers = dedupe(papers)
    gurus = dedupe(gurus, url_key="url", title_key="quoteTitle")
    youtube = dedupe(youtube, url_key="url", title_key="videoTitle")

    # 품질 필터링 (URL 필수, 출처 상한, 과장/광고 감지, 출처 불명확 구루 제외)
    filtered = apply_quality_filters(
        {"articles": articles, "papers": papers,
         "guruMentions": gurus, "youtubeBriefs": youtube},
        source_reg.get("defaults", {}),
        youtube_reg.get("defaults", {}),
    )
    articles = filtered["articles"]
    papers = filtered["papers"]
    gurus = filtered["guruMentions"]
    youtube = filtered["youtubeBriefs"]

    # 누적 일수 = data/daily 의 날짜 스냅샷 개수 (오늘 포함)
    os.makedirs(DAILY_DIR, exist_ok=True)
    existing_days = {f[:-5] for f in os.listdir(DAILY_DIR) if f.endswith(".json")}
    existing_days.add(today)
    cumulative_days = len(existing_days)

    payload = {
        "date": today,
        "updatedAt": now_iso,
        "stats": {
            "cumulativeDays": cumulative_days,
            "articleCount": len(articles),
            "guruMentionCount": len(gurus),
            "youtubeBriefCount": len(youtube),
            "paperCount": len(papers),
            "sourceCount": len(used_sources),
        },
        "dailyInsight": {},
        "articles": articles,
        "guruMentions": gurus,
        "youtubeBriefs": youtube,
        "papers": papers,
        "reportSummary": {},
    }

    # LLM 요약 훅: summarize_with_llm.py 가 있고 API 키가 있으면 고품질 요약으로 교체
    enriched = None
    try:
        from summarize_with_llm import enrich  # 3단계에서 추가됨
        log("INFO", "summarize_with_llm 감지 → LLM 요약 시도")
        enriched = enrich(payload)
    except ImportError:
        log("INFO", "summarize_with_llm 없음 → fallback 요약 사용")
    except Exception as e:  # noqa: BLE001
        log("WARN", f"LLM 요약 실패 → fallback 사용: {e}")

    payload = enriched if enriched else fallback_enrich(payload)

    write_json(os.path.join(DATA_DIR, "latest.json"), payload)
    write_json(os.path.join(DAILY_DIR, f"{today}.json"), payload)

    s = payload["stats"]
    log("DONE", (
        f"뉴스 {s['articleCount']} / 구루 {s['guruMentionCount']} / "
        f"유튜브 {s['youtubeBriefCount']} / 논문 {s['paperCount']} / "
        f"출처 {s['sourceCount']} / 누적 {s['cumulativeDays']}일"
    ))


if __name__ == "__main__":
    main()
