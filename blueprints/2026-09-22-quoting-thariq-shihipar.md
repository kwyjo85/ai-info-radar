# Claude Code AGENTS.md 지원 및 커스텀 Mods 도입 블루프린트

## 개요
Claude Code 2.1.277부터 폴더에 CLAUDE.md가 없으면 AGENTS.md를 자동으로 인식해 프로젝트 지침으로 사용한다. 이 기능은 "Claude Code mods"라는 새로운 하네스 커스터마이징 메커니즘 위에 내장 mod로 구현되어 있으며, 공개된 소스를 참고하면 자신만의 커스텀 mod를 만들어 Claude Code 동작을 확장할 수 있다.

## 구현 가능성 — 상
Claude Code CLI를 최신 버전으로 업데이트하기만 하면 AGENTS.md 인식은 즉시 사용 가능하고, mods 소스는 GitHub에 공개되어 있어 개인 MacBook에서 설치·실습이 바로 가능하다. 다만 커스텀 mod 제작은 공식 문서가 아직 부족해 소스 코드를 직접 읽어야 하는 진입장벽이 있다.

## 필요 도구
- **Claude Code CLI** (무료, `npm install -g @anthropic-ai/claude-code`) — 2.1.277 이상 필요
- **Node.js** — Claude Code 실행 런타임 (무료)
- **Git / GitHub CLI(`gh`)** — mods 저장소 클론용 (무료)
- **anthropics/claude-code GitHub 저장소**의 `mods/agents-md`, `mods/` 디렉토리 — 무료, 공개 소스 (https://github.com/anthropics/claude-code/tree/main/mods)
- 텍스트 에디터 (VS Code 등, 무료)

## 구현 단계
1. `claude --version`으로 현재 버전을 확인하고, 2.1.277 미만이면 `claude update` 또는 `npm update -g @anthropic-ai/claude-code`로 업데이트한다.
2. 테스트용 디렉토리를 하나 만들고, 프로젝트 개요·코딩 컨벤션·빌드/테스트 명령 등 기존 CLAUDE.md와 동일한 내용을 담은 `AGENTS.md` 파일을 작성한다.
3. 해당 디렉토리에 CLAUDE.md가 없는 상태로 `claude`를 실행해 AGENTS.md 지침이 정상적으로 로드되는지 확인한다 (예: AGENTS.md에만 넣은 특이 지침을 Claude가 실제로 따르는지로 검증).
4. 같은 폴더에 CLAUDE.md를 추가로 만들어보고, CLAUDE.md가 우선 적용되어 AGENTS.md가 무시되는지 재확인해 우선순위 규칙을 직접 확인한다.
5. `git clone https://github.com/anthropics/claude-code`로 저장소를 받고 `mods/agents-md` 디렉토리 소스를 읽어 mod의 구조(트리거 조건, 파일 탐색·로딩 로직)를 파악한다.
6. `mods/` 아래 다른 예시 mod들도 훑어보며 입력/출력 인터페이스와 등록 방식 등 공통 패턴을 정리한다.
7. (선택, 심화) 본인 워크플로우에 맞는 간단한 커스텀 mod를 하나 작성해 로컬에서 로드·테스트한다 — 예: 특정 파일명 규칙을 프로젝트 지침 파일로 추가 인식하게 하는 mod.
8. 실습 결과를 바탕으로 본인 프로젝트들의 CLAUDE.md/AGENTS.md 사용 정책(어느 파일을 표준으로 쓸지)을 정리해 개인 컨벤션 문서에 반영한다.

## 예상 공수
- CLI 업데이트 및 AGENTS.md 기본 동작 확인: 15~30분
- mods 소스 코드 읽고 구조 파악: 30분~1시간
- 커스텀 mod 제작 실습(선택): 1~3시간, 공식 문서 부재로 소스 리딩에 시간 소요
- 전체 난이도: **하** (기본 AGENTS.md 사용) / **중~상** (커스텀 mod 제작)

## 리스크/유의점
- mods는 "upcoming" 기능으로 막 공개된 상태라 API/구조가 아직 안정화되지 않았을 가능성이 높음 — 커스텀 mod를 만들어도 향후 버전에서 호환성이 깨질 수 있음.
- 한 폴더에 CLAUDE.md와 AGENTS.md가 동시에 있으면 CLAUDE.md가 우선 적용되므로, 마이그레이션 시 혼란을 피하려면 프로젝트별로 둘 중 하나만 유지할 것.
- 정보 출처가 X(트위터) 공지와 GitHub 소스 수준에 머물러 있어 공식 문서가 부족하며, 세부 동작은 직접 실습으로 검증해야 한다.
- 외부(오픈소스 등)에서 받은 AGENTS.md나 커스텀 mod 파일은 프로젝트 지침으로 자동 로드되므로, 신뢰할 수 없는 저장소를 클론해 그대로 사용할 경우 프롬프트 인젝션 위험을 고려해 내용을 먼저 검토할 것.

---
원본: https://simonwillison.net/2026/Sep/18/thariq-shihipar/
