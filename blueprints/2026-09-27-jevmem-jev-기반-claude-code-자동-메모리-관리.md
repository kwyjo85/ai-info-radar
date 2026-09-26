# Jevmem: Jev 기반 Claude Code 자동 메모리 관리

## 쉽게 말하면
Claude Code로 코딩할 때마다 "우리 SQLite 쓰기로 했잖아... 아 Postgres로 바꿨었지" 하며 매번 처음부터 설명해야 했던 걸, 이 도구가 대화 내용에서 결정·규칙·버그·할일을 자동으로 받아 적어뒀다가 다음 세션에 슬쩍 알려주는 개인 비서 역할을 합니다. 마치 회의록을 아무도 안 시켰는데 알아서 써주는 신입사원 같은 존재이며, 마음이 바뀌면 예전 메모를 지우지 않고 "이건 취소됨"이라고 표시만 해둡니다.

## 이걸로 할 수 있는 것
1. Jev 관련 자동화 프로젝트를 여러 세션에 걸쳐 작업할 때, "왜 이 방식으로 했더라"를 매번 다시 설명하지 않아도 Claude Code가 이전 결정을 기억하고 시작합니다.
2. 여러 클라이언트에게 Claude Code 기반 자동화를 납품/운영할 때, 프로젝트별 제약사항(예: "이 클라이언트는 Node 20만 지원")을 자동 기록해 실수로 위반하는 걸 방지합니다.
3. ai-info-radar 같은 개인 프로젝트에서 launchd 설정, 배포 방식, 후순위 기능 목록 등을 CLAUDE.md에 수작업으로 유지보수하는 대신 대화 중 자동으로 누적시킵니다.

## 개요
이 도구는 Claude Code(및 Cursor, Codex)와의 대화에서 나온 결정·제약·버그·할일을 Jev(TypeSafe AI) 모델로 판별해 JEVMEM.md 파일에 한 줄씩 기록하고, 다음 세션 시작 시 관련 내용을 자동으로 컨텍스트에 주입하는 프로젝트 메모리 시스템입니다. 반복 설명 시간을 줄여 실제 자동화·수익화 작업(예: Jev 활용 서비스 개발, 여러 프로젝트 동시 관리)에 쓸 시간을 늘려주는 게 핵심 가치이며, 특히 여러 프로젝트를 오가며 Claude Code로 수익을 내려는 1인 운영자에게 컨텍스트 손실 비용을 줄여줍니다.

## 구현 가능성: 상
- 이미 npm 패키지 + Claude Code 플러그인 마켓플레이스로 배포되어 있어 설치 자체가 60초 내외로 표준화되어 있음
- macOS(Darwin) 환경을 명시적으로 지원하며(PATH 탐색 경로에 /opt/homebrew/bin, ~/.nvm 등 포함), 현재 사용자의 zsh + Claude Code 환경과 정확히 일치
- 사용자가 이미 Jev(TypeSafe AI)를 알고 있고 키 발급 경험이 있을 가능성이 높아 진입장벽 낮음

## 필요 도구
- Node.js 20+ (무료, 이미 설치되어 있을 가능성 높음)
- jevmem npm 패키지 (무료, MIT 등 오픈소스 추정)
- Claude Code CLI + 플러그인 마켓플레이스 기능 (이미 사용 중이면 무료)
- TypeSafe AI 계정 및 API 키 (Jev 모델 사용, 무료 티어 여부는 가입 시 확인 필요 — 유료 가능성 있음)
- (선택) OpenAI 또는 Anthropic API 키 — writer 옵션으로 메모 문장을 더 압축하고 싶을 때만, 사용량 기반 과금

## 구현 단계
1. `npm install -g jevmem`으로 CLI 전역 설치 후 `jevmem doctor`로 환경 점검
2. TypeSafe AI 사이트에서 계정 생성 후 API 키 발급 (Jev 모델 접근용)
3. `claude plugin marketplace add Avinash-jetwani/jevmem` → `claude plugin install jevmem@jevmem` 실행
4. Claude Code 내에서 `/plugin configure jevmem@jevmem`으로 TypeSafe 키 입력 (안전 저장소에 보관됨)
5. 대상 프로젝트(예: ai-info-radar) 디렉터리로 이동 후 `jevmem enable` 실행해 옵트인
6. 기존 CLAUDE.md/AGENTS.md가 있다면 `jevmem import --apply`로 기존 규칙을 JEVMEM.md 형식으로 이관
7. 며칠간 실제 Claude Code 세션을 진행하며 JEVMEM.md에 어떤 내용이 자동 기록되는지 확인, 필요시 jevmem.config.json에서 저장 임계값 조정
8. (선택) writer를 Anthropic/OpenAI로 설정해 메모 문장 품질을 높일지 결정 — 이때 비용 발생 인지
9. 여러 프로젝트(수익화용 클라이언트 프로젝트 포함)에 동일 방식으로 확대 적용, .gitignore에 .jevmem/ 포함 여부 검토

## 예상 공수
- 초기 설치·설정: 30분~1시간 (난이도: 하)
- 기존 CLAUDE.md 이관 및 검증: 1~2시간 (난이도: 중, import 결과를 사람이 검토해야 함)
- 여러 프로젝트로 확대 적용 및 안정화: 2~3시간 (난이도: 중)
- 전체: 반나절 이내로 완결 가능한 소규모 도구

## 리스크/유의점
- TypeSafe AI(Jev) 서비스 자체가 신생/외부 의존 서비스이므로, 키 유출이나 서비스 중단 시 메모리 기능이 멈출 수 있음 (다만 로컬 대화 진행 자체는 영향 없음)
- writer로 OpenAI/Anthropic을 설정하면 매 턴마다 소량이라도 API 비용이 누적될 수 있으므로 클라이언트 프로젝트에 적용 시 비용 고지 필요
- 메모리 포이즈닝 방어 기능이 있다고 하나 100% 차단은 아님(테스트에서 22개 중 2개 미차단) — 팀 협업 시 신뢰 경계 설정 필요
- 오픈소스 저장소(Avinash-jetwani/jevmem)가 개인 개발자 프로젝트로 보이므로 유지보수 지속성·보안 감사 여부를 설치 전 직접 확인 권장
- PRIVACY.md에 텔레메트리 없음을 명시하나, 클라이언트 민감 정보가 포함된 프로젝트에 적용 시 스크러빙(secret 제거) 로직이 완벽한지 직접 검증 필요

---
원본: https://github.com/Avinash-jetwani/jevmem
