# AI 뉴스레터 자동화 플랫폼

AI 뉴스·논문·구루 발언·테크 유튜버 소식을 매일 수집하고, LLM이 전문 에디터처럼 재구성하여
마케팅/전략 실무자가 바로 활용할 수 있는 한국어 뉴스레터 대시보드로 보여주는 MVP.

매일 아침 이 페이지를 열면 다음 질문에 바로 답할 수 있는 것이 목표다.

- 오늘 AI 업계에서 중요한 변화는 무엇인가?
- 주요 AI 리더들은 어떤 방향을 말하고 있는가?
- 신뢰할 만한 테크 유튜버들은 어떤 소식을 전하고 있는가?
- 어떤 논문/연구가 실무적으로 의미 있는가?
- 마케팅/브랜드/컨텐츠 전략에 어떤 영향을 주는가?
- 임원 보고에는 어떤 문장으로 정리할 수 있는가?

## 페이지 구성

1. 오늘의 AI 인사이트
2. 핵심 뉴스
3. AI 구루 최신 언급
4. 테크 유튜버 브리프
5. 논문 / 리서치
6. 보고용 서머리

## 파일 구조

```
ai-newsletter/
├── index.html              # 대시보드 (UI)            ✅ 완료
├── styles.css              # 스타일                    ✅ 완료
├── app.js                  # data/latest.json 렌더링   ✅ 완료
├── scrape_daily.py         # 뉴스/논문/유튜브/구루 수집  ✅ 완료
├── summarize_with_llm.py   # LLM 요약·인사이트·서머리    ✅ 완료
├── source-registry.json    # 뉴스/논문 소스 레지스트리   ✅ 완료
├── people-registry.json    # AI 구루 레지스트리          ✅ 완료
├── youtube-registry.json   # 유튜버 채널 레지스트리      ✅ 완료
├── requirements.txt        # 파이썬 의존성               ✅ 완료
├── .env.example            # API 키 템플릿               ✅ 완료
├── data/
│   ├── latest.json         # 최신 결과 (UI가 읽는 파일)  ✅ 스키마 초기화
│   └── daily/YYYY-MM-DD.json # 일자별 스냅샷
└── README.md
```

## 데이터 스키마 (`data/latest.json`)

```json
{
  "date": "YYYY-MM-DD",
  "updatedAt": "ISO timestamp",
  "stats": { "cumulativeDays": 0, "articleCount": 0, "guruMentionCount": 0,
             "youtubeBriefCount": 0, "paperCount": 0, "sourceCount": 0 },
  "dailyInsight": {},
  "articles": [],
  "guruMentions": [],
  "youtubeBriefs": [],
  "papers": [],
  "reportSummary": {}
}
```

## 라이브 데모

- 배포 URL: https://hazajous-code.github.io/ai-newsletter-claude/
- 정적 호스팅이므로 화면은 저장소에 커밋된 `data/latest.json` 을 표시한다.
  데이터를 갱신하려면 로컬에서 `python scrape_daily.py` 실행 후 `data/latest.json` 을 커밋/푸시한다.

## 실행 방식

### 사전 준비: Python 설치

Windows 에서 `python` 이 Microsoft Store 안내로 연결되면 실제 인터프리터가 없는 상태다.
[python.org](https://www.python.org/downloads/) 에서 설치하거나(설치 시 "Add to PATH" 체크),
`winget install Python.Python.3.12` 로 설치한 뒤 새 터미널에서 `python --version` 으로 확인한다.

### 실행

```bash
pip install -r requirements.txt
cp .env.example .env        # API 키 입력 (없어도 fallback 동작)
python scrape_daily.py      # 수집 → (키 있으면) LLM 요약까지 자동 → data/latest.json 생성
python -m http.server 8090
# http://127.0.0.1:8090 접속
```

- `scrape_daily.py` 는 수집 후 `summarize_with_llm.py` 의 `enrich()` 를 자동 호출한다.
- API 키가 없으면 fallback 요약으로 기본 화면이 보이고, 키가 있으면 LLM 기반 고품질 요약이 작동한다.
- 이미 수집된 데이터만 다시 요약하려면: `python summarize_with_llm.py`

### LLM 공급자

`.env` 의 `LLM_PROVIDER`(기본 `anthropic`)가 우선 공급자를 정하며, 해당 공급자 호출이
실패하면 다른 공급자 키가 있을 경우 자동 폴백한다. SDK 없이 `requests` 로 직접 호출하므로
추가 의존성이 없다.

## 수집 원칙

- X/Twitter는 직접 크롤링하지 않고 RSS·공식 블로그·Substack 등 공개 소스만 사용한다.
- 출처 링크가 명확한 내용만 수집하며, 발언자/직함/맥락/날짜를 함께 보존한다.
- 카테고리·태그·검색 등 목록 페이지는 제외하고 실제 기사 상세 페이지만 유지한다.
- 중복을 제거하고 출처별 최대 노출 개수를 제한한다.
- 한 소스가 실패해도 전체 수집은 멈추지 않는다.

## 개발 진행 단계

- **1단계 (완료)** — 파일 구조 + 3개 레지스트리 + 설정 파일
- **2단계 (완료)** — 뉴스/논문/유튜브/구루 수집 + 기본 UI
- **3단계 (완료)** — LLM 요약 모듈 연결 (기사/구루/유튜브/논문 + 인사이트/서머리)
- **4단계 (완료)** — 품질 필터링 강화(광고성/과장 감지·출처 상한·출처 불명확 구루 제외) + 교차 연결 정교화
- **5단계 (완료)** — UI 정리(자막/설명 기반 표시 등) + GitHub Pages 배포

## 배포 (GitHub Pages)

`main` 브랜치에 push 하면 `.github/workflows/deploy.yml` 이 정적 사이트를 Pages 로 배포한다.
최초 1회, 저장소 **Settings → Pages → Build and deployment → Source** 를 **GitHub Actions** 로
지정해야 워크플로가 동작한다(이미 Actions 소스면 자동 배포).

### 품질 필터링 (스펙 9절)

`scrape_daily.py` 의 `apply_quality_filters()` 가 중복 제거 직후 적용된다.

- URL/제목 없는 항목 제거
- 출처별 전역 노출 상한(`cap_per_source`)
- 구루 발언 중 출처 링크 없는 항목 제외(출처 불명확 차단)
- 유튜브 과장/광고성 제목 감지(`detect_hype`) → `hypeFlag`, 검증 필요 표시, 신뢰도 baseline 하향
- LLM 단계는 `hypeFlag` 를 힌트로 더 보수적으로 평가하며, 휴리스틱이 의심한 영상의 검증 필요는 LLM이 끄지 못한다
