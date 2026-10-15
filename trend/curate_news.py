#!/usr/bin/env python3
"""
AI Trend Search — '오늘의 AI 뉴스' 큐레이션

기존 scrape_daily.py 가 만든 data/latest.json(글로벌·한국 매체 수집본)에서
AI 관련성과 중요도가 높은 기사만 골라 trend/data/news.json 을 만든다.

- 글로벌 최대 6건, 한국 최대 5건 (피로도 방지)
- 최근 3일 이내 기사만, 같은 매체 최대 2건, 비슷한 제목은 1건만
- 점수 = AI 관련성 + 빅테크/주요 기업 + 마케팅 영향 + 출시/정책 + 최신성 + 매체 신뢰도
"""
import json, os, re, datetime, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "latest.json")
REG = os.path.join(ROOT, "source-registry.json")
OUT_DIR = os.path.join(ROOT, "trend", "data")
OUT = os.path.join(OUT_DIR, "news.json")
TR = os.path.join(OUT_DIR, "translations.json")  # 영문 기사 한국어 제목·요약 캐시 (URL 키)

LIMIT = {"global": 6, "korea": 5}
MAX_AGE_DAYS = 3
PER_SOURCE = 2
MIN_SCORE = 5  # 이 점수 미만은 아무리 기사가 적어도 노출하지 않음

AI_TERMS = [r"(?-i:(?<![A-Za-z])AI(?![A-Za-z]))", r"\bA\.I\.", r"artificial intelligence", r"(?-i:(?<![A-Za-z])LLMs?(?![A-Za-z]))", r"(?-i:(?<![A-Za-z])GPT(?![A-Za-z]))", r"chatgpt", r"\bagents?\b", r"agentic",
            r"openai", r"anthropic", r"claude", r"gemini", r"deepmind", r"copilot", r"\bmuse\b", r"llama", r"grok", r"mistral",
            r"machine learning", r"neural", r"model", r"chatbot", r"generative",
            "인공지능", "에이전트", "챗GPT", "오픈AI", "앤트로픽", "제미나이", "생성형", r"(?-i:(?<![A-Za-z])LLM(?![A-Za-z]))", r"(?-i:(?<![A-Za-z])AX(?![A-Za-z]))", "딥마인드", "코파일럿", "모델", r"(?-i:(?<![A-Za-z])AI(?![A-Za-z]))"]
BIG = [r"chatgpt", r"gemini", r"claude", r"copilot", r"\bmuse\b", r"llama", r"grok", "챗GPT", "제미나이", "클로드", "코파일럿", r"openai", r"anthropic", r"google", r"deepmind", r"\bmeta\b", r"microsoft", r"apple", r"nvidia", r"amazon", r"xai", r"tiktok", r"adobe",
       "오픈AI", "앤트로픽", "구글", "메타", "마이크로소프트", r"(?-i:(?<![A-Za-z])MS(?![A-Za-z]))", "애플", "엔비디아", "아마존", "삼성", "네이버", "카카오", r"(?-i:(?<![A-Za-z])LG(?![A-Za-z]))", r"(?-i:(?<![A-Za-z])SK(?![A-Za-z]))", "현대", "어도비"]
MARKETING = [r"advertis", r"\bads?\b", r"marketing", r"brand", r"commerce", r"shopping", r"retail", r"search", r"creator", r"copyright", r"slop",
             "광고", "마케팅", "브랜드", "커머스", "쇼핑", "검색", "크리에이터", "저작권", "유통", "이커머스"]
MARKETING_STRICT = [r"advertis", r"marketing", r"e-?commerce", r"shopping", r"\bslop\b", "광고", "마케팅", "커머스", "쇼핑"]
# 기업 공식 블로그: 출시 발표가 아니면 홍보·고객 사례로 보고 감점
OWNED = {"openai-blog", "google-deepmind", "google-ai-blog", "microsoft-ai-blog", "meta-ai-blog", "nvidia-blog", "anthropic-blog"}
PROMO = [r"^how ", r"customer", r"case study", r"partner", r"invest", r"powered", r"deploy", r"builds?\b", r"building", r"\bcuts?\b", r"puts? .* to work", r"collaborat", r"ecosystem"]
LAUNCH = [r"(?:gemini|gpt|claude|llama|grok|muse)[- ]?\d", r"launch", r"release", r"unveil", r"introduc", r"announce", r"rolls? out", "출시", "공개", "발표", "도입", "선보"]
POLICY = [r"regulat", r"lawsuit", r"\bsues?\b", r"court", r"ban", r"policy", r"security", r"safety", r"antitrust",
          "규제", "소송", "피소", "법안", "정책", "보안", "안전", "제재", "표준"]
# 홍보성·저관련 신호
NOISE = [r"^the download", r"newsletter", r"podcast", r"\bdeals?\b", r"\bsale\b", r"best .* to buy", r"how to watch",
         r"^\[AI 리더스\]", "코스닥", "상장", "인터뷰", "집중 조명", "도약", "가속", "영토", "CPI", "비트코인", "호랑이", "부고", "인사"]

def has(pats, text):
    return sum(1 for p in pats if re.search(p, text, re.I))

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def norm_title(t):
    t = re.sub(r"\[[^\]]*\]", " ", t.lower())
    return set(w for w in re.findall(r"[0-9a-z가-힣]+", t) if len(w) > 1)

def score(a, trust, now, source_id=""):
    title = a.get("title", "")
    desc = a.get("description", "") or ""
    text = f"{title} {desc}"
    ai_t, ai_d = has(AI_TERMS, title), has(AI_TERMS, desc)
    if ai_t == 0:  # 제목에 AI 관련어가 없으면 제외
        return None, []
    if has(NOISE, title):
        return None, []
    s, tags = 0.0, []
    s += 2 if ai_t else 1
    if has(BIG, text):
        s += 2; tags.append("빅테크")
    if has(MARKETING, title) or has(MARKETING_STRICT, desc):
        s += 2.5; tags.append("마케팅 영향")
    if has(LAUNCH, title):
        s += 1; tags.append("출시·발표")
    if has(POLICY, text):
        s += 1; tags.append("정책·법·보안")
    dt = parse_dt(a.get("publishedAt"))
    if dt:
        age = (now - dt).total_seconds() / 86400
        if age > MAX_AGE_DAYS:
            return None, []
        s += 2 if age <= 1 else 1
    if trust == "high" and source_id not in OWNED:
        s += 1
    if source_id in OWNED and has(PROMO, title):
        s -= 3
    if source_id in OWNED and re.search(r"responsib|safely|system card|model card", title, re.I):
        s -= 0.5  # 같은 출시의 부속 글보다 본 발표 글을 우선
    return s, tags[:2]

def main():
    if not os.path.exists(SRC):
        print("[curate] data/latest.json 없음 — 건너뜀"); return 0
    data = json.load(open(SRC, encoding="utf-8"))
    reg = {s["id"]: s for s in json.load(open(REG, encoding="utf-8")).get("newsSources", [])}
    now = datetime.datetime.now(datetime.timezone.utc)
    tr = json.load(open(TR, encoding="utf-8")) if os.path.exists(TR) else {}

    pools = {"global": [], "korea": []}
    for a in data.get("articles", []):
        src = reg.get(a.get("sourceId"), {})
        region = src.get("region", "global")
        if region not in pools:
            continue
        sc, tags = score(a, a.get("trust") or src.get("trust"), now, a.get("sourceId", ""))
        if sc is None:
            continue
        pools[region].append({
            "title": a.get("title", "").strip(),
            "url": a.get("url"),
            "source": a.get("sourceName") or src.get("name", ""),
            "sourceId": a.get("sourceId"),
            "publishedAt": a.get("publishedAt", ""),
            "summary": re.sub(r"\s+", " ", (a.get("summaryKo") or a.get("description") or "")).strip()[:(110 if region == "korea" else 170)],
            "lang": a.get("lang") or src.get("language", ""),
            "titleKo": "",
            "summaryKo": "",
            "tags": tags,
            "score": round(sc, 2),
        })

    out = {"date": data.get("date"), "updatedAt": now.astimezone(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="minutes"),
           "global": [], "korea": []}
    for region, items in pools.items():
        items.sort(key=lambda x: (x["score"], x["publishedAt"]), reverse=True)
        picked, per, seen = [], {}, []
        for it in items:
            if per.get(it["sourceId"], 0) >= PER_SOURCE:
                continue
            nt = norm_title(it["title"])
            # 다른 매체끼리는 제목 50% 이상, 같은 매체끼리는 25% 이상 겹치면 같은 이야기로 보고 1건만
            if any(len(nt & s) / max(1, min(len(nt), len(s))) >= (0.25 if sid == it["sourceId"] else 0.5) for s, sid in seen):
                continue
            picked.append(it); seen.append((nt, it["sourceId"])); per[it["sourceId"]] = per.get(it["sourceId"], 0) + 1
            if len(picked) >= LIMIT[region]:
                break
        picked = [p for p in picked if p["score"] >= MIN_SCORE]
        picked.sort(key=lambda x: x["publishedAt"], reverse=True)
        # 영문 기사: LLM 번역(summarize_with_llm)이 있으면 사용, 없으면 번역 캐시 사용
        src_by_url = {a.get("url"): a for a in data.get("articles", [])}
        for it in picked:
            if it["lang"] == "ko" or region == "korea":
                continue
            a = src_by_url.get(it["url"], {})
            if a.get("titleKo") and a.get("titleKo") != a.get("title"):
                it["titleKo"], it["summaryKo"] = a["titleKo"], a.get("summaryKo", "")
            elif it["url"] in tr:
                it["titleKo"], it["summaryKo"] = tr[it["url"]].get("titleKo", ""), tr[it["url"]].get("summaryKo", "")
        out[region] = picked

    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[curate] global {len(out['global'])} / korea {len(out['korea'])} → {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
