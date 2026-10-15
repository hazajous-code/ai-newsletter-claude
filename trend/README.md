# AI Trend Search (마케터용 주간 AI 트렌드 뉴스레터)

- 최신 호: `trend/index.html` → Pages 주소 `/trend/`
- 지난 호: `trend/issues/YYYY-MM-DD.html`, 목록은 `trend/archive.html`
- 조사 키워드: `trend/keywords.json` — `always`(상시)와 `focus`(이번 호 집중 주제)를 수정하면 다음 발행부터 반영
- 디자인: 흰 배경, `trend/style.css` 공통 사용

## 발행 절차 (자동 예약 작업이 따르는 규칙)
1. keywords.json의 키워드로 최근 7일 뉴스 검색
2. 섹션: EDITOR'S NOTE(히어로 카피) → 3줄 요약 → 커버스토리 → 에이전트 → AI 슬롭 워치 → 마케터 체크리스트 → 출처
3. `issues/<날짜>.html` 생성, `index.html`을 최신 호로 교체, `archive.html`의 ARCHIVE:START 바로 아래에 한 줄 추가
4. main에 커밋·푸시 → GitHub Pages 자동 배포
