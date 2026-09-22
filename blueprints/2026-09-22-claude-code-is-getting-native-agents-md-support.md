# Claude Code의 AGENTS.md 네이티브 지원 도입

## 개요
Claude Code가 별도의 `CLAUDE.md` 없이도 `AGENTS.md` 파일을 프로젝트 설정 파일로 직접 인식하도록 업데이트되었습니다. 이는 여러 AI 코딩 도구(Codex, Cursor, Aider 등)가 공통으로 채택하고 있는 `AGENTS.md` 표준에 Claude Code가 합류함을 의미하며, 하나의 설정 파일로 여러 AI 도구를 동시에 운용할 수 있어 중복 관리 부담을 줄여줍니다.

## 구현 가능성 — 상
- MacBook에서 진행 중인 `ai-info-radar` 프로젝트에 `AGENTS.md` 파일 하나만 추가하면 즉시 적용 가능하며, 별도 인프라나 외부 API가 필요 없습니다.
- Claude Code CLI가 이미 로컬에 설치되어 사용 중이므로 추가 설치 비용 없이 마이그레이션만 하면 됩니다.

## 필요 도구
- Claude Code CLI (이미 사용 중, 무료/구독 기반)
- 텍스트 에디터 (VS Code 등, 무료)
- Git (버전 관리, 무료)
- 선택: Codex, Cursor 등 AGENTS.md를 지원하는 타 AI 도구 (교차 호환성 테스트용, 각 도구별 별도 라이선스/구독 필요)

## 구현 단계
1. 현재 `ai-info-radar` 저장소 루트에 `CLAUDE.md`가 있는지 확인한다 (`ls CLAUDE.md`).
2. 있다면 내용을 그대로 복사해 `AGENTS.md`로 저장한다 (`cp CLAUDE.md AGENTS.md`).
3. Claude Code 최신 버전으로 업데이트한다 (`claude update` 또는 `npm install -g @anthropic-ai/claude-code@latest`).
4. `AGENTS.md`만 남기고 `CLAUDE.md`를 제거할지, 두 파일을 병행 유지할지 결정한다. 다른 AI 도구(Cursor, Codex 등)를 함께 쓴다면 `AGENTS.md` 단일화가 유리하다.
5. Claude Code를 재시작해 `AGENTS.md` 내용이 정상적으로 로드되는지 확인한다 (간단한 질문으로 프로젝트 규칙을 알고 있는지 테스트).
6. 기존에 프로젝트별로 흩어져 있던 다른 도구용 설정 파일(`.cursorrules`, `.aider.conf` 등)이 있다면 `AGENTS.md`로 통합할 수 있는지 검토한다.
7. `git add AGENTS.md && git commit -m "chore: migrate to AGENTS.md"`로 커밋한다.

## 예상 공수
- 총 소요 시간: 15~30분
- 난이도: 하 (파일 이름 변경 및 CLI 업데이트 수준의 작업)

## 리스크/유의점
- Claude Code 버전이 오래되면 `AGENTS.md`를 인식하지 못할 수 있으므로 반드시 최신 버전 확인이 필요하다.
- `CLAUDE.md`와 `AGENTS.md`가 동시에 존재할 때의 우선순위 동작(공식 문서 기준 `CLAUDE.md`가 없을 때만 `AGENTS.md`를 읽음)을 정확히 확인하지 않으면 설정이 무시될 수 있다.
- 팀/협업 환경이 아닌 개인 프로젝트이므로 리스크는 낮으나, 여러 저장소에 걸쳐 있다면 마이그레이션 체크리스트를 만들어 일괄 적용하는 것이 안전하다.

---
원본: https://github.com/anthropics/claude-code/tree/main/mods/agents-md
