# Jev × Universal Search MCP: 워크스페이스 트리아지 에이전트 수익화

## 개요
Google의 Universal Search MCP Server는 Gmail·Drive·Docs·Calendar를 하나의 MCP 인터페이스로 통합 검색하게 해주는데, 매 검색 결과를 LLM에 그대로 넘기면 토큰 비용이 급증한다. Jev(TypeSafe AI System One)를 1차 필터로 앞단에 배치해 검색 결과를 "타입(청구서/회의요청/스팸/액션필요 등) + 확신도"로 즉시 분류하고, 확신도가 높은 항목만 LLM으로 넘겨 요약·초안 작성을 시키면 비용을 100분의 1 수준으로 줄이면서 실시간 트리아지 SaaS를 개인 MacBook에서도 운영 가능한 마진으로 만들 수 있다.

## 구현 가능성 — 중
- Universal Search MCP Server 자체는 Google이 공개 문서화한 표준 MCP 서버라 통합 난이도는 낮음(상 수준).
- 다만 Jev API의 실제 스펙(입력 스키마, 타입 정의 방식, 요금제)이 아직 공개 초기 단계라 프로덕션 연동 세부사항 확정에 시간이 걸릴 수 있어 종합적으로는 "중"으로 평가.
- 개인 MacBook에서 MCP 클라이언트 + 경량 오케스트레이션 스크립트만으로 PoC는 즉시 가능.

## 필요 도구
- **Universal Search MCP Server** (Google Workspace, 무료 — Workspace API 사용량에 따라 과금 가능성 있음)
- **Jev API (TypeSafe AI System One)** — 유료, 사용량 기반 과금 (LLM 대비 저가 티어 예상)
- **Claude/GPT 등 LLM API** — 최종 요약·응답 생성용, 유료 (Jev로 호출량 절감 목표)
- **Node.js 또는 Python MCP 클라이언트 SDK** — 무료 오픈소스
- **Google Cloud OAuth 2.0 클라이언트** — Workspace API 접근용, 무료
- **로컬 큐/스케줄러** (예: cron, 또는 node-cron) — 무료
- **Stripe 또는 Lemon Squeezy** — 구독 결제 처리용, 거래 수수료 발생

## 구현 단계
1. Google Cloud Console에서 프로젝트 생성 후 Workspace API(Gmail, Drive, Calendar) OAuth 2.0 클라이언트 등록, 필요한 스코프(읽기 전용부터 시작) 발급.
2. Universal Search MCP Server를 로컬(MacBook)에 배포하고, MCP 클라이언트로 검색 쿼리 테스트(예: "지난 7일 미답변 이메일" 검색).
3. Jev API 계정 생성 후, 검색 결과 텍스트를 입력으로 넣어 "카테고리(청구서/미팅/액션필요/일반)" + "확신도(0~1)" 타입 값을 반환받는 파이프라인 스크립트 작성.
4. 확신도 임계값(예: 0.85 이상) 기준으로 라우팅 로직 구성: 고확신 항목만 LLM으로 전달해 요약/초안 생성, 저확신 항목은 별도 검토 큐에 적재.
5. 결과를 노션/슬랙/이메일 다이제스트 형태로 매일 발송하는 알림 레이어 구축.
6. 3~5명의 베타 사용자(1인 기업가, 프리랜서 등) 대상 무료 트라이얼 진행, LLM 호출량 절감률과 정확도 로그 수집.
7. Stripe 연동해 월 구독제(예: $15~30/월) SaaS로 전환, 비용 절감 데이터를 마케팅 근거로 활용.

## 예상 공수
- PoC(1~6단계 중 6단계 이전): 20~30시간, 난이도 중
- 결제·구독 전환 및 안정화(7단계): 추가 15~20시간, 난이도 중~상 (OAuth 보안, 요금제 설계 포함)
- 총 예상: 약 1~1.5개월(파트타임 기준)

## 리스크/유의점
- Jev API가 신규 출시 모델이라 요금제/레이트리밋/타입 스키마 커스터마이징 범위가 아직 불확실 — 실제 계약 전 최신 공식 문서 재확인 필요.
- Gmail/Drive 데이터에 접근하므로 OAuth 스코프 최소화와 사용자 데이터 저장 정책(암호화, 보존기간)을 명확히 해야 함 — 개인정보 취급 방침 미비 시 규제 리스크.
- 분류 확신도 임계값을 잘못 설정하면 중요 이메일이 저확신 큐에 묻힐 수 있어, 초기에는 사람이 큐를 병행 검토하는 안전장치 필요.
- Google Workspace API 자체의 쿼터 제한으로 다수 사용자 확장 시 API 사용량 관리가 필요.

---
원본: https://developers.google.com/workspace/guides/universal-search-mcp
