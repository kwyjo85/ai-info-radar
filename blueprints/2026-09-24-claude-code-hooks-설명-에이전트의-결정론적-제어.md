# Claude Code Hooks: 에이전트의 결정론적 제어

## 쉽게 말하면
Claude Code Hooks는 AI 에이전트가 파일을 수정하거나 명령을 실행하기 "직전"과 "직후"에 내가 정한 규칙을 무조건 실행시키는 장치입니다. 비유하자면 AI 비서에게 자유롭게 일을 맡기되, 문 앞에 "이 서류는 꼭 검토 도장을 받아야 나갈 수 있음" 같은 검문소를 세워두는 것과 같습니다. AI의 판단(확률적)과 별개로, 검문소 자체는 100% 예측 가능하게 작동합니다.

## 이걸로 할 수 있는 것
1. Claude Code가 코드를 수정할 때마다 자동으로 포맷터·린터를 돌려서 품질을 항상 일정하게 유지한다.
2. `ai-info-radar` 프로젝트의 블루프린트 파일이 생성될 때마다 자동으로 git add/commit 트리거를 걸어 수작업 커밋을 없앤다.
3. 클라이언트에게 납품하는 Claude Code 기반 자동화 패키지에 "위험한 명령(rm -rf, force push 등) 자동 차단" 안전장치를 넣어 신뢰도 높은 유료 상품으로 판매한다.

## 개요
Hooks는 PreToolUse(도구 실행 전), PostToolUse(실행 후), UserPromptSubmit, Stop, Notification 등 특정 이벤트 시점에 셸 명령을 강제 실행하는 설정(JSON, settings.json)입니다. AI의 "알아서 잘 하겠지"에 의존하지 않고, 포맷팅·보안 검사·로깅·알림·커밋 같은 규칙을 코드로 못박아 자동화 파이프라인의 안정성을 높입니다. 이는 Claude Code를 단순 코딩 도우미가 아니라 "감독관이 붙은 자동화 엔진"으로 격상시키는 핵심 기능입니다.

## 구현 가능성
**상** — 근거: Hooks는 Claude Code에 이미 내장된 공식 기능이며(`update-config` 스킬로 설정 가능), 설정 파일(JSON) 작성과 셸 스크립트 작성만으로 끝나 추가 인프라나 외부 API 계약이 필요 없습니다. macOS 로컬 환경에서 바로 테스트 가능하며, 이미 사용자의 `ai-info-radar` 프로젝트에도 launchd·gh-pages 자동화 경험이 있어 진입장벽이 낮습니다.

## 필요 도구
- Claude Code CLI (이미 사용 중, 무료/구독 포함)
- `settings.json` / `.claude/settings.local.json` 편집 — 무료, 내장 기능
- macOS 셸(zsh) 스크립트 작성 — 무료
- (선택) `jq` — JSON 파싱, 무료 (brew install jq)
- (선택) `terminal-notifier` 또는 macOS 알림 센터 연동 — 무료
- (선택, 상품화 시) 클라이언트별 배포용 GitHub 저장소/템플릿 — 무료(Public) 또는 GitHub 유료 플랜

## 구현 단계
1. `update-config` 스킬 또는 직접 `.claude/settings.json`을 열어 hooks 항목 구조(PreToolUse/PostToolUse/Stop 등)를 확인한다.
2. 가장 쉬운 예시부터 시작: PostToolUse 훅으로 파일 편집 후 자동 `prettier`/`black` 실행 스크립트를 등록해 테스트한다.
3. `ai-info-radar` 프로젝트에 맞는 실전 훅 설계: 블루프린트(`blueprints/*.md`) 파일이 새로 생성되면 PostToolUse 훅이 `git add`를 자동 실행하도록 구성한다.
4. 위험 명령 차단용 PreToolUse 훅 작성 — `rm -rf`, `git push --force`, `git reset --hard` 같은 패턴을 정규식으로 감지해 차단하는 셸 스크립트를 만든다.
5. Stop 훅으로 세션 종료 시 요약 로그를 파일(예: `logs/session-log.md`)에 자동 기록해 "무엇을 자동화했는지" 증거를 남긴다.
6. 검증한 hooks 세트를 템플릿화(`hooks-template/` 디렉토리 + README)하여, 이후 Claude Code 자동화 컨설팅/코칭 상품 판매 시 "안전장치 내장 패키지"로 제공한다.
7. (수익화 단계) Upwork/크몽 등에서 "Claude Code 안전 자동화 세팅"을 상품화하고, 이 hooks 템플릿을 데모 영상과 함께 홍보한다.

## 예상 공수
- 기본 훅 1~2개 세팅 및 테스트: 1~2시간, 난이도 하
- ai-info-radar용 자동 커밋 훅 구축: 2~3시간, 난이도 중
- 위험 명령 차단 + 로깅 등 완성형 템플릿화: 4~6시간, 난이도 중
- 상품화(문서화, 데모, 판매 페이지)까지: 추가 3~5시간, 난이도 중

## 리스크/유의점
- PreToolUse 훅이 잘못 작성되면 정상 작업까지 차단해 Claude Code 자체가 멈출 수 있음 — 항상 테스트 브랜치에서 먼저 검증.
- 훅 스크립트에 민감 정보(토큰, API 키)를 하드코딩하면 git 커밋 시 유출 위험 — 환경변수로 분리.
- 자동 커밋/자동 push 훅은 "리뷰 없는 배포"로 이어질 수 있어, 최소한 커밋까지만 자동화하고 push는 수동 확인 단계를 유지하는 것을 권장.
- 클라이언트에게 판매할 경우, 훅이 클라이언트의 기존 워크플로우(CI/CD, 팀 규칙)와 충돌하지 않는지 사전 확인 필요.

---
원본: https://blakecrosley.com/blog/claude-code-hooks-explained
