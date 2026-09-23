# llm-typesafe로 Jev 붙이기 — CLI 한 줄로 만드는 "이메일/티켓 자동 분류" 유료 자동화 서비스

## 개요
`llm-typesafe`는 Simon Willison의 `llm` CLI에 Jev(TypeSafe AI System One)를 연결하는 플러그인으로, `llm -m jev -s "질문"` 한 줄로 yes/no(noul), 다중분류(choice), 점수(score) 판정을 텍스트 생성 없이 즉시 받아온다. LLM 호출 대비 100배 빠르고 저렴하다는 특성 덕분에, 이메일·CS 티켓·PR·리뷰 같은 대량 텍스트를 "분류/라우팅/스코어링"하는 반복 업무를 매우 낮은 원가로 자동화할 수 있어, 이를 소상공인/1인 개발자용 저가 SaaS나 사내 워크플로우 자동화 상품으로 판매하는 것이 핵심 수익 모델이다.

## 구현 가능성 — 중
- CLI 플러그인 설치와 셸 파이프라인 구성 자체는 macOS에서 몇 시간 내 가능할 정도로 단순함(`llm install llm-typesafe` + API 키 설정).
- 다만 Jev는 2026년 9월 출시된 신모델로 API 키가 대기열(waitlist) 기반이라 "지금 바로" 키를 받을 수 있을지 불확실하며, 요금제·쿼터·SLA 정보가 아직 공개적으로 충분치 않음.
- 대기열 통과 전까지는 동일한 인터페이스(noul/choice/score)를 텍스트 임베딩+분류기로 흉내 내며 파이프라인을 먼저 완성해둘 수 있어, "상"은 아니지만 "중" 이상으로 평가.

## 필요 도구
- `llm` CLI (Simon Willison, 무료, 오픈소스) — https://llm.datasette.io/
- `llm-typesafe` 플러그인 (무료, 오픈소스, `pip install llm-typesafe` 또는 `llm install llm-typesafe`)
- TypeSafe AI Jev API 키 (유료, 대기열 신청 필요 — console.typesafe.ai)
- macOS 표준 `mail`/IMAP 접근 또는 Gmail API (무료 티어 존재, 이메일 연동 시)
- Zapier 또는 n8n (자체 호스팅 시 무료, 클라우드 사용 시 유료 — 비개발자 고객 대상 워크플로우 연결용)
- Python 3.11+ 또는 bash 스크립트 (무료, 파이프라인 오케스트레이션)
- SQLite 또는 Notion API (무료/부분 유료, 분류 결과 저장 및 대시보드화)
- Stripe (유료, 서비스화 시 구독 결제 연동)
- launchd (macOS 내장, 무료 — 정기 실행 스케줄링)

## 구현 단계
1. macOS에 `pipx install llm` 후 `llm install llm-typesafe`로 플러그인 설치, TypeSafe AI 콘솔에서 API 키 대기열 신청 및 `llm keys set typesafe` 등록.
2. 키 발급 전까지는 README 예시(`-s '환불을 명시적으로 요청하는가?'` 같은 noul 질문, billing/technical/other 같은 choice 질문, 재현성 점수 같은 score 질문)를 그대로 실행해 입출력 포맷과 지연시간을 손에 익힌다.
3. 실제 타깃 데이터 소스 하나를 정한다 — 예: 특정 Gmail 라벨의 CS 문의 메일, 혹은 GitHub 레포의 이슈. IMAP/Gmail API 또는 `gh issue list --json body`로 텍스트를 로컬로 가져오는 스크립트를 작성.
4. 각 텍스트에 대해 `llm -m jev -s ... -o answer_type choice -o criteria '{...}'`를 호출해 "billing/technical/other" 같은 카테고리와 확신도(confidence)를 받아오는 파이프라인 스크립트(Python subprocess 또는 bash)를 작성하고 결과를 SQLite에 적재.
5. 확신도가 낮은(예: 0.6 미만) 항목은 자동 분류하지 않고 "검토 필요" 큐로 분리하는 임계값 로직을 추가해 오분류 리스크를 낮춘다.
6. 분류 결과에 따라 Slack 알림, Notion 데이터베이스 카드 생성, 또는 담당팀 이메일 포워딩 등 후속 액션을 n8n/Zapier 워크플로우로 연결.
7. launchd로 10~30분 주기 실행 스케줄을 등록하고, 처리 로그(원문 앞부분, 분류 결과, 확신도, 처리 시각)를 남겨 나중에 정확도 검증에 쓴다.
8. 지인/소규모 팀 1~2곳을 대상으로 무료 파일럿을 돌려 정확도와 처리 속도를 검증한 뒤, 월 구독제(예: 워크스페이스당 월 3~10만원) 소규모 SaaS 또는 컨설팅형 "자동화 셋업 대행" 상품으로 전환.

## 예상 공수
- 1~3단계 (환경 구성 및 데이터 소스 연동): 4~6시간
- 4~5단계 (분류 파이프라인 및 신뢰도 임계값 로직): 6~10시간
- 6~7단계 (후속 액션 연동 및 스케줄링): 5~8시간
- 8단계 (파일럿 및 상품화 준비): 8~15시간
- 총 23~39시간, 난이도: 중 (CLI/스크립팅 경험만 있으면 충분하나, Jev API 키 확보 시점에 따라 일정이 좌우됨)

## 리스크/유의점
- Jev API 키가 대기열제라 확보 시점을 통제할 수 없음 — 착수 전 신청부터 먼저 넣고, 승인 전까지는 대체 분류기(임베딩+로지스틱 회귀)로 파이프라인을 완성해두는 것을 권장.
- 이메일/티켓 원문에는 개인정보·결제정보가 포함될 수 있으므로, 외부 API(Jev)로 전송하기 전 고객 동의 및 데이터 처리 방침을 명확히 해야 함(특히 유료 서비스화 시).
- 확신도 임계값을 너무 낮게 잡으면 오분류로 인한 고객 신뢰 손상 위험이 있으므로, 초기에는 "자동 처리 + 사람 검수" 하이브리드로 운영하며 임계값을 데이터 기반으로 조정할 것.
- 신생 모델/플러그인이라 API 스펙(파라미터명, 응답 포맷)이 변경될 가능성이 있어, 파이프라인은 `llm` CLI 래퍼 계층을 두어 하위 모델 교체가 쉽도록 설계.
- 원문은 개인 개발자의 오픈소스 플러그인 공지 수준으로 상업적 검증 사례는 아직 없음 — 상품화 전 소규모 파일럿으로 실제 비용 절감/정확도를 먼저 수치로 확인 필요.

---
원본: https://simonwillison.net/2026/Sep/22/llm-typesafe/

---
원본: https://simonwillison.net/2026/Sep/22/llm-typesafe/
