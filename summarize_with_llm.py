#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_with_llm.py — LLM 기반 한국어 요약/재구성 모듈

역할:
  - scrape_daily.py 가 수집한 raw payload 를 받아 전문 에디터 톤의 한국어 카드로 재구성한다.
  - Anthropic(우선) / OpenAI(폴백) 를 SDK 없이 requests 로 직접 호출한다.
  - API 키가 하나도 없으면 enrich() 는 None 을 반환하고, scrape_daily.py 는 fallback 요약을 사용한다.
  - 항목별 호출이 실패해도 해당 카드만 원문 기반(llm=False)으로 두고 전체는 계속 진행한다.

에디터 원칙(스펙 5절):
  - 원문을 이해한 뒤 자연스러운 한국어로 재작성(직역 금지, 반복 금지)
  - 마케팅/전략 실무자·임원 보고 관점 반영
  - 과장 축소, 사실과 해석 구분

직접 실행:
  python summarize_with_llm.py        # data/latest.json 을 다시 요약해 덮어씀
"""

import os
import re
import sys
import json
import time

try:
    import requests
except ImportError:
    print("[FATAL] requests 가 필요합니다. pip install -r requirements.txt")
    sys.exit(1)

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
PREFERRED = os.getenv("LLM_PROVIDER", "").strip().lower()

# Claude Platform on AWS (Anthropic 직접 운영, SigV4 + workspace_id)
# 모델 ID는 접두사 없는 그대로의 ID(claude-opus-4-8 등)를 사용한다 — Bedrock의 anthropic. 접두사 아님.
AWS_REGION = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip()
AWS_WORKSPACE_ID = os.getenv("ANTHROPIC_AWS_WORKSPACE_ID", "").strip()
AWS_MODEL = os.getenv("AWS_MODEL", ANTHROPIC_MODEL).strip()

SYSTEM_PROMPT = (
    "당신은 AI·테크 분야를 다루는 한국어 전문 에디터입니다. "
    "마케팅 기획자, 디지털 전략 담당자, 임원 보고 담당자가 바로 활용할 수 있도록 글을 재구성합니다. "
    "원문을 이해한 뒤 자연스러운 한국어로 다시 쓰고, 직역과 반복 문장을 피합니다. "
    "과장된 표현은 줄이고 근거 중심으로 쓰며, 사실과 해석을 구분합니다. "
    "반드시 요청된 JSON 형식 하나만 출력하고 그 외 텍스트는 출력하지 않습니다."
)


# --------------------------------------------------------------------------- #
# 공급자 호출 (requests 직접)
# --------------------------------------------------------------------------- #
def _aws_configured():
    """Claude Platform on AWS 사용 조건: region + workspace_id 지정.
    자격증명(AWS_ACCESS_KEY_ID/SECRET 또는 역할/프로파일)은 SDK가 표준 체인에서 해석."""
    return bool(AWS_REGION and AWS_WORKSPACE_ID)


def _providers():
    """사용 가능한 공급자를 우선순위대로 반환. 기본 순서: aws → anthropic → openai.
    LLM_PROVIDER 가 지정되면 그 공급자를 맨 앞으로 올린다."""
    avail = []
    if _aws_configured():
        avail.append("aws")
    if ANTHROPIC_KEY:
        avail.append("anthropic")
    if OPENAI_KEY:
        avail.append("openai")
    if PREFERRED in avail:
        avail.remove(PREFERRED)
        avail.insert(0, PREFERRED)
    return avail


_AWS_CLIENT = None


def _aws_client():
    """AnthropicAWS 클라이언트 싱글턴. region/workspace_id 는 환경변수에서, 자격증명은 SigV4 체인에서."""
    global _AWS_CLIENT
    if _AWS_CLIENT is None:
        from anthropic import AnthropicAWS  # pip install "anthropic[aws]"
        _AWS_CLIENT = AnthropicAWS()
    return _AWS_CLIENT


def _call_aws(user_prompt, max_tokens=1024):
    client = _aws_client()
    resp = client.messages.create(
        model=AWS_MODEL,                # 접두사 없는 ID
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(
        getattr(b, "text", "") for b in resp.content
        if getattr(b, "type", None) == "text"
    )


def _call_anthropic(user_prompt, max_tokens=1024):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []))


def _call_openai(user_prompt, max_tokens=1024):
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _extract_json(text):
    """LLM 응답에서 첫 JSON 객체를 안전하게 추출."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


def llm_json(user_prompt, max_tokens=1024, retry=1):
    """공급자 폴백 + 재시도. 성공 시 dict, 전부 실패 시 None."""
    for provider in _providers():
        for _ in range(retry + 1):
            try:
                if provider == "aws":
                    raw = _call_aws(user_prompt, max_tokens)
                elif provider == "anthropic":
                    raw = _call_anthropic(user_prompt, max_tokens)
                else:
                    raw = _call_openai(user_prompt, max_tokens)
                parsed = _extract_json(raw)
                if parsed is not None:
                    return parsed
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] {provider} 호출 실패: {e}", flush=True)
                time.sleep(0.8)
    return None


# --------------------------------------------------------------------------- #
# 항목별 요약
# --------------------------------------------------------------------------- #
def _as_list(v, n=None):
    if isinstance(v, list):
        out = [str(x).strip() for x in v if str(x).strip()]
    elif v:
        out = [str(v).strip()]
    else:
        out = []
    return out[:n] if n else out


def summarize_article(a):
    prompt = (
        "다음 AI/테크 기사를 마케팅·전략 실무자 관점에서 한국어로 재구성하라.\n"
        f"제목: {a.get('title','')}\n"
        f"출처: {a.get('sourceName','')}\n"
        f"본문 요약(원문): {a.get('description','')}\n\n"
        "아래 JSON 키로만 출력:\n"
        '{"titleKo":"한국어 제목","summaryKo":"2~3문장 한국어 요약",'
        '"insights":["인사이트1","인사이트2","인사이트3"],'
        '"keyPoints":["핵심 포인트","핵심 포인트"],'
        '"soWhat":"마케팅/비즈니스 관점 So What 한 문장",'
        '"execLine":"임원 보고용 한 줄"}'
    )
    r = llm_json(prompt)
    if not r:
        return False
    a["titleKo"] = r.get("titleKo") or a.get("title", "")
    a["summaryKo"] = r.get("summaryKo") or a.get("description", "")
    a["insights"] = _as_list(r.get("insights"), 3)
    a["keyPoints"] = _as_list(r.get("keyPoints"))
    a["soWhat"] = (r.get("soWhat") or "").strip()
    a["execLine"] = (r.get("execLine") or "").strip()
    a["llm"] = True
    return True


def summarize_guru(g):
    prompt = (
        "다음은 AI 분야 저명 인사의 공개 발언/글이다. 출처가 분명한 내용만 요약하라.\n"
        f"인물: {g.get('name','')} ({g.get('title','')}, {g.get('org','')})\n"
        f"제목: {g.get('quoteTitle','')}\n"
        f"내용(원문): {g.get('quoteText','')}\n\n"
        "아래 JSON 키로만 출력:\n"
        '{"summaryKo":"발언 요약(한국어 2~3문장)",'
        '"meaning":"핵심 의미 한 문장",'
        '"businessImplication":"마케팅/비즈니스 시사점 한 문장",'
        '"caution":"주의해서 봐야 할 점 한 문장"}'
    )
    r = llm_json(prompt)
    if not r:
        return False
    g["summaryKo"] = r.get("summaryKo") or g.get("quoteText", "")
    g["meaning"] = (r.get("meaning") or "").strip()
    g["businessImplication"] = (r.get("businessImplication") or "").strip()
    g["caution"] = (r.get("caution") or "").strip()
    g["llm"] = True
    return True


def summarize_youtube(y):
    transcript = y.get("transcriptExcerpt", "")
    basis = "자막 일부" if transcript else "제목+설명"
    hype_hint = (
        "사전 휴리스틱이 이 영상을 과장/광고성으로 의심했다. 더 보수적으로 평가하라.\n"
        if y.get("hypeFlag") else ""
    )
    prompt = (
        "다음은 테크 유튜브 영상이다. 자극적 제목을 그대로 믿지 말고, "
        "정보성/광고성을 구분하여 한국어로 요약하라.\n"
        f"채널: {y.get('channelName','')}\n"
        f"영상 제목: {y.get('videoTitle','')}\n"
        f"설명(원문): {y.get('description','')}\n"
        f"{'자막 일부: ' + transcript if transcript else ''}\n"
        f"(요약 근거: {basis})\n"
        f"{hype_hint}\n"
        "신뢰도 기준 — high: 공식 채널/전문가 인터뷰/기술 데모, "
        "medium: 분석형 유튜버, low: 과장성 제목/출처 불명확.\n"
        "아래 JSON 키로만 출력:\n"
        '{"summaryKo":"핵심 내용 요약(한국어)",'
        '"keyPoints":["포인트1","포인트2","포인트3"],'
        '"implication":"마케팅/컨텐츠/비즈니스 관점 실무 시사점",'
        '"trust":"high|medium|low",'
        '"needsVerification":true 또는 false}'
    )
    r = llm_json(prompt)
    if not r:
        return False
    y["summaryKo"] = r.get("summaryKo") or y.get("description", "")
    y["keyPoints"] = _as_list(r.get("keyPoints"), 3)
    y["implication"] = (r.get("implication") or "").strip()
    trust = str(r.get("trust", "")).lower().strip()
    y["trust"] = trust if trust in ("high", "medium", "low") else y.get("baselineTier", "medium")
    # 휴리스틱이 과장/광고로 의심했다면 검증 필요는 유지(LLM이 끄지 못함)
    y["needsVerification"] = bool(r.get("needsVerification", False)) or bool(y.get("hypeFlag"))
    y["llm"] = True
    return True


def summarize_paper(p):
    prompt = (
        "다음 논문을 비전문가도 이해할 수 있게 한국어로 정리하라.\n"
        f"제목: {p.get('title','')}\n"
        f"초록/설명(원문): {p.get('description','')}\n\n"
        "아래 JSON 키로만 출력:\n"
        '{"titleKo":"한국어 제목","topic":"연구 주제",'
        '"contribution":"핵심 기여(한국어 2문장)",'
        '"applicability":"실무 적용 가능성",'
        '"marketingAngle":"마케팅/컨텐츠 관점 의미",'
        '"difficulty":"상|중|하"}'
    )
    r = llm_json(prompt)
    if not r:
        return False
    p["titleKo"] = r.get("titleKo") or p.get("title", "")
    p["topic"] = (r.get("topic") or "").strip()
    p["contribution"] = r.get("contribution") or p.get("description", "")
    p["applicability"] = (r.get("applicability") or "").strip()
    p["marketingAngle"] = (r.get("marketingAngle") or "").strip()
    diff = str(r.get("difficulty", "")).strip()
    p["difficulty"] = diff if diff in ("상", "중", "하") else "중"
    p["llm"] = True
    return True


# --------------------------------------------------------------------------- #
# 종합: 오늘의 인사이트 / 보고용 서머리
# --------------------------------------------------------------------------- #
def _snip(text, n=120):
    text = (text or "").strip()
    return text[:n] + ("…" if len(text) > n else "")


def _digest(payload, limit=20):
    """교차 연결 품질을 위해 제목 + 짧은 요약 스니펫 + 링크를 함께 제공."""
    lines = []
    for a in payload.get("articles", [])[:8]:
        lines.append(
            f"[뉴스/{a.get('sourceName','')}] {a.get('titleKo') or a.get('title','')}"
            f" — {_snip(a.get('summaryKo') or a.get('description',''))} | {a.get('url','')}"
        )
    for g in payload.get("guruMentions", [])[:5]:
        lines.append(
            f"[구루/{g.get('name','')}] {g.get('quoteTitle','')}"
            f" — {_snip(g.get('summaryKo') or g.get('quoteText',''))} | {g.get('url','')}"
        )
    for y in payload.get("youtubeBriefs", [])[:4]:
        lines.append(
            f"[유튜브/{y.get('channelName','')}] {y.get('videoTitle','')}"
            f" — {_snip(y.get('summaryKo') or y.get('description',''))} | {y.get('url','')}"
        )
    for p in payload.get("papers", [])[:4]:
        lines.append(
            f"[논문] {p.get('titleKo') or p.get('title','')}"
            f" — {_snip(p.get('contribution') or p.get('description',''))} | {p.get('url','')}"
        )
    return "\n".join(lines[:limit])


def build_daily_insight(payload):
    digest = _digest(payload)
    if not digest:
        return None
    prompt = (
        "다음은 오늘 수집된 AI 동향 목록이다. 전략 보고서 톤으로 '오늘의 AI 인사이트'를 작성하라. "
        "과장 없이 간결하게, 뉴스/구루/유튜브/논문 간 연결점을 짚어라.\n\n"
        f"{digest}\n\n"
        "아래 JSON 키로만 출력:\n"
        '{"headline":"오늘 가장 중요한 흐름 한 줄",'
        '"body":"3~5문장 분석. 시장 변화와 마케팅 실무자에게 중요한 이유 포함",'
        '"connections":["서로 다른 소스 간 연결점1","연결점2"],'
        '"watchNext":["다음에 확인할 포인트1","포인트2"]}'
    )
    r = llm_json(prompt, max_tokens=1200)
    if not r:
        return None
    return {
        "headline": (r.get("headline") or "오늘의 AI 인사이트").strip(),
        "body": (r.get("body") or "").strip(),
        "connections": _as_list(r.get("connections")),
        "watchNext": _as_list(r.get("watchNext")),
        "llm": True,
    }


def build_report_summary(payload):
    digest = _digest(payload)
    if not digest:
        return None
    prompt = (
        "다음 오늘의 AI 동향을 바탕으로 임원 보고에 그대로 옮길 수 있는 '보고용 서머리'를 작성하라.\n\n"
        f"{digest}\n\n"
        "topTrends 는 최대 5개. evidenceUrl 은 위 목록의 실제 링크를 사용하라.\n"
        "아래 JSON 키로만 출력:\n"
        '{"topTrends":[{"title":"트렌드","evidenceUrl":"근거 링크",'
        '"soWhat":"의미 한 문장","quote":"있으면 핵심 인용, 없으면 빈 문자열"}],'
        '"actions":["실행 제안1","실행 제안2"],'
        '"risks":["리스크/유의점1","유의점2"]}'
    )
    r = llm_json(prompt, max_tokens=1400)
    if not r:
        return None
    trends = []
    for t in (r.get("topTrends") or [])[:5]:
        if not isinstance(t, dict):
            continue
        trends.append({
            "title": (t.get("title") or "").strip(),
            "evidenceUrl": (t.get("evidenceUrl") or "").strip(),
            "soWhat": (t.get("soWhat") or "").strip(),
            "quote": (t.get("quote") or "").strip(),
        })
    return {
        "topTrends": trends,
        "actions": _as_list(r.get("actions")),
        "risks": _as_list(r.get("risks")),
        "llm": True,
    }


# --------------------------------------------------------------------------- #
# 항목 실패 시 원문 기반 카드 (부분 실패 격리)
# --------------------------------------------------------------------------- #
def _raw_article(a):
    a.setdefault("titleKo", a.get("title", ""))
    a.setdefault("summaryKo", a.get("description", ""))
    a.setdefault("insights", [])
    a.setdefault("keyPoints", [])
    a.setdefault("soWhat", "")
    a.setdefault("execLine", "")
    a["llm"] = False


def _raw_guru(g):
    g.setdefault("summaryKo", g.get("quoteText", ""))
    g.setdefault("meaning", "")
    g.setdefault("businessImplication", "")
    g.setdefault("caution", "")
    g["llm"] = False


def _raw_youtube(y):
    y.setdefault("summaryKo", y.get("description", ""))
    y.setdefault("keyPoints", [])
    y.setdefault("implication", "")
    y.setdefault("trust", y.get("baselineTier", "medium"))
    y.setdefault("needsVerification", False)
    y["llm"] = False


def _raw_paper(p):
    p.setdefault("titleKo", p.get("title", ""))
    p.setdefault("topic", "")
    p.setdefault("contribution", p.get("description", ""))
    p.setdefault("applicability", "")
    p.setdefault("marketingAngle", "")
    p.setdefault("difficulty", "")
    p["llm"] = False


# --------------------------------------------------------------------------- #
# LLM 종합 실패 시 카운트/기사 기반 폴백 (키 없거나 호출 실패)
# --------------------------------------------------------------------------- #
def _fallback_insight(payload):
    a, g = len(payload.get("articles", [])), len(payload.get("guruMentions", []))
    y, p = len(payload.get("youtubeBriefs", [])), len(payload.get("papers", []))
    return {
        "headline": "오늘 수집된 AI 동향 요약",
        "body": (
            f"오늘 뉴스 {a}건, AI 구루 발언 {g}건, 테크 유튜브 {y}건, 논문 {p}건을 수집했습니다. "
            "LLM 요약을 활성화하면(.env 에 유효한 API 키 입력) 전문 에디터 톤의 한국어 인사이트와 "
            "소스 간 연결점이 자동 생성됩니다."
        ),
        "connections": [],
        "watchNext": [],
        "llm": False,
    }


def _fallback_report(payload):
    top = payload.get("articles", [])[:5]
    return {
        "topTrends": [
            {"title": a.get("titleKo") or a.get("title", ""),
             "evidenceUrl": a.get("url", ""), "soWhat": "", "quote": ""}
            for a in top
        ],
        "actions": [],
        "risks": [],
        "llm": False,
    }


# --------------------------------------------------------------------------- #
# 진입점: enrich(payload)
# --------------------------------------------------------------------------- #
def enrich(payload):
    """scrape_daily.py 가 호출. API 키 없으면 None 반환(→ fallback 사용)."""
    providers = _providers()
    if not providers:
        print("[INFO] LLM API 키 없음 → enrich 생략", flush=True)
        return None
    print(f"[INFO] LLM 요약 시작 (공급자 우선순위: {', '.join(providers)})", flush=True)

    ok = 0
    fail = 0
    for a in payload.get("articles", []):
        if summarize_article(a):
            ok += 1
        else:
            _raw_article(a); fail += 1
    for g in payload.get("guruMentions", []):
        if summarize_guru(g):
            ok += 1
        else:
            _raw_guru(g); fail += 1
    for y in payload.get("youtubeBriefs", []):
        if summarize_youtube(y):
            ok += 1
        else:
            _raw_youtube(y); fail += 1
    for p in payload.get("papers", []):
        if summarize_paper(p):
            ok += 1
        else:
            _raw_paper(p); fail += 1

    insight = build_daily_insight(payload)
    payload["dailyInsight"] = insight if insight else _fallback_insight(payload)
    report = build_report_summary(payload)
    payload["reportSummary"] = report if report else _fallback_report(payload)

    print(f"[DONE] LLM 카드 생성 성공 {ok} / 원문 대체 {fail}", flush=True)
    return payload


def _standalone():
    path = os.path.join(BASE_DIR, "data", "latest.json")
    if not os.path.exists(path):
        print("[FATAL] data/latest.json 이 없습니다. 먼저 python scrape_daily.py 실행")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out = enrich(payload)
    if out is None:
        print("[INFO] API 키가 없어 변경 없음")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] {path} 갱신 완료")


if __name__ == "__main__":
    _standalone()
