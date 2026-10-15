# AI Trend Search (마케터용 주간 AI 트렌드 뉴스레터)

- 최신 호: `trend/index.html` → Pages 주소 `/trend/`
- 지난 호: `trend/issues/YYYY-MM-DD.html`, 목록은 `trend/archive.html`
- 조사 키워드: `trend/keywords.json` — `always`(상시)와 `focus`(이번 호 집중 주제)를 수정하면 다음 발행부터 반영
- 디자인: 흰 배경, `trend/style.css` 공통 사용

## 발행 절차 (자동 예약 작업이 따르는 규칙)
1. keywords.json의 키워드로 최근 7일 뉴스 검색
2. 레이아웃: 화면 전체 너비를 쓰는 컨설팅 보고서(장표) 스타일. 텍스트 나열 대신 구조화 컴포넌트 사용
   - HERO: 메인 메시지 카피 + 우측 개념 비교 도식(hof-grid)
   - 핵심 수치 4칸(stats)
   - 각 섹션(board): 번호 헤더 → 회색 요약 박스(summary) → 좌측 개념 패널(concept + arrow-down) / 우측 타임라인(tl, card)
   - 필요 시: 카드 그리드(games), 막대 비교(bars), 스펙트럼(spectrum), 흐름도(flow / hflow), 폰 목업(phones), 사례 카드(cases), 비교 매트릭스(matrix), 체크리스트 카드(checks)
   - 각 섹션 끝에 '마케터 시선'(insight) 바, 핵심 문구는 빨간 강조(b.r), 보조 수치는 초록 주석(.g)
   - 섹션 순서: HERO → 수치 → 01 커버스토리 → 02 에이전트 → 03 AI 슬롭 워치 → 04 마케터 체크리스트 → 출처
3. `issues/<날짜>.html` 생성, `index.html`을 최신 호로 교체, `archive.html`의 ARCHIVE:START 바로 아래에 한 줄 추가
4. main에 커밋·푸시 → GitHub Pages 자동 배포
