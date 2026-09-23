# awesome-jev 큐레이션 모니터링으로 Jev 수익화 아이디어 자동 발굴하기

## 개요
awesome-jev는 TypeSafe AI의 Jev(System One) 모델을 활용한 X(트위터) 데모, 도구, 스킬, 통합 사례를 모아놓은 큐레이션 저장소입니다. 이 저장소를 정기적으로 모니터링하고, 새로 추가된 항목을 Jev 자체(타입 값+확신도 즉시 반환, LLM 대비 100배 빠르고 저렴)로 자동 분류·스코어링해 "수익화 가능성이 높은 사례"만 걸러내면, 매번 수동으로 GitHub을 뒤지지 않고도 실전 사례를 빠르게 발굴해 자신의 프로젝트(예: ai-info-radar 블루프린트 파이프라인)에 재활용할 수 있습니다. 특히 분류·필터링 단계를 LLM 대신 Jev로 처리하면 반복 실행 비용을 크게 낮출 수 있다는 점이 핵심 가치입니다.

## 구현 가능성 — 상
근거: (1) GitHub 공개 저장소의 README/커밋을 읽는 것은 API 호출만으로 가능해 기술적 장벽이 낮음, (2) 이미 사용자가 ai-info-radar 저장소에서 RSS 수집→블루프린트 생성 파이프라인을 운영 중이라 동일한 아키텍처(수집→파싱→분류→저장→알림)를 그대로 재사용 가능, (3) Jev의 "텍스트 대신 타입 값+확신도 반환" 특성이 "이 항목은 수익화 관련 도구인가/데모인가/스킬인가"를 판별하는 단순 분류 작업에 정확히 들어맞아 별도 프롬프트 엔지니어링 부담이 적음. 다만 Jev API가 2026-09 출시된 신규 서비스라 공식 문서·SDK 성숙도를 직접 확인해야 하는 점은 감안 필요.

## 필요 도구
- **GitHub REST API 또는 `gh` CLI** — 무료 (인증 토큰 기반 rate limit 있음)
- **Jev API (TypeSafe AI System One)** — 유료, 사용량 기반 과금 (API 키 발급 필요, 콘솔에서 확인)
- **Python 3 + requests, PyGithub** — 무료
- **SQLite 또는 로컬 JSON 파일** — 무료, 이미 발견한 항목 중복 방지용 저장소
- **macOS `launchd`** — 무료, 정기 실행 스케줄러 (cron 대체)
- **Slack/Telegram Webhook (선택)** — 무료 티어로 충분, 새 항목 알림용
- **기존 ai-info-radar 블루프린트 생성 스크립트** — 재사용 (신규 개발 불요)

## 구현 단계
1. GitHub API로 `Amal-David/awesome-jev` 저장소의 최신 커밋 SHA와 README 원문을 가져오는 스크립트를 작성한다 (`GET /repos/{owner}/{repo}/commits` + `GET /repos/{owner}/{repo}/readme`).
2. 로컬에 저장된 마지막 확인 커밋 SHA와 비교해 변경분이 있을 때만 다음 단계로 진행하도록 diff 체크 로직을 넣는다 (불필요한 API/Jev 호출 방지).
3. README의 마크다운 링크 목록(`[이름](URL) - 설명`)을 정규식 또는 마크다운 파서로 파싱해 `{name, url, description}` 구조로 추출한다.
4. 추출된 각 항목을 Jev API에 전달해 타입 스키마 기반 분류를 수행한다 — 예: `category: enum(demo, tool, skill, integration)`, `monetization_potential: enum(low, medium, high)`, `confidence: float`. LLM 프롬프트 대신 Jev의 타입-값 반환 방식을 그대로 활용.
5. SQLite에 `url`을 unique key로 하여 upsert하고, 이미 처리한 항목은 재분류하지 않도록 한다.
6. `monetization_potential: high` && `confidence > 0.7` 조건을 만족하는 신규 항목만 필터링해 ai-info-radar의 기존 블루프린트 생성 스크립트에 입력으로 전달, 자동으로 구현 블루프린트 초안을 생성한다.
7. `launchd` plist를 작성해 하루 1회(예: 매일 오전 9시) 스크립트를 실행하도록 등록한다 (`~/Library/LaunchAgents/com.airadar.awesomejev.plist`).
8. 새 고잠재력 항목 발견 시 Slack/Telegram 웹훅으로 요약(이름, URL, 카테고리, 확신도)을 전송해 수동 검토를 트리거한다.

## 예상 공수
- GitHub 수집 + diff 체크 스크립트: 1.5시간
- Jev API 연동 및 분류 스키마 설계: 2~3시간 (신규 API라 문서 확인 시간 포함)
- SQLite 저장/중복 제거 로직: 1시간
- launchd 스케줄 등록 + 알림 웹훅: 1시간
- 기존 블루프린트 파이프라인과 통합 테스트: 1.5~2시간
- 총 예상: 7~9시간
- 난이도: 중 (개별 요소는 단순하지만 Jev API가 신규 서비스라 스키마 설계 시행착오 가능)

## 리스크/유의점
- Jev API는 2026-09 출시된 신규 서비스로 SDK/문서가 아직 안정화되지 않았을 수 있으므로, 실제 요청/응답 포맷을 콘솔이나 공식 문서에서 먼저 검증한 뒤 스키마를 확정할 것.
- awesome-jev 저장소가 개인이 관리하는 큐레이션 리스트라 업데이트 빈도가 낮거나 중단될 가능성이 있어, 일일 폴링보다 주간 폴링으로 낮춰 불필요한 API 호출을 줄이는 것을 고려.
- GitHub API rate limit(비인증 시간당 60회)에 걸릴 수 있으므로 개인 액세스 토큰(PAT)을 발급해 인증 요청(시간당 5,000회)으로 전환할 것.
- "수익화 가능성" 분류는 결국 주관적 판단이므로, Jev의 확신도 점수를 맹신하지 말고 주 1회 수동 리뷰로 오탐(false positive)을 걸러내는 절차를 유지할 것.
- API 키(Jev, GitHub PAT)는 `.env` 파일 등으로 분리 관리하고 절대 커밋하지 않도록 `.gitignore`에 등록.

---
원본: https://github.com/Amal-David/awesome-jev

---
원본: https://github.com/Amal-David/awesome-jev
