# Jira 프로젝트 헬스 감사기 (MCP Server) 구축

## 개요
Jira REST API를 MCP(Model Context Protocol) 서버로 감싸서, Claude 등 AI 에이전트가 스프린트 정체 이슈·미배정 티켓·오래된 스토리·라벨/우선순위 불일치 등을 자동으로 점검하고 주간 "프로젝트 건강 리포트"를 생성하도록 만드는 작업이다. 매니저가 수동으로 Jira 보드를 훑어보는 시간을 줄이고, 문제가 곪기 전에 조기에 알려주는 것이 핵심 가치다.

## 구현 가능성 — 상
- Jira REST API v3는 공식 문서와 인증(API 토큰) 방식이 안정적이고, MCP 서버는 Python/TypeScript SDK로 수십~수백 줄 수준의 얇은 래퍼로 구현 가능.
- 참고 리포지토리(`jira-ai-auditor`)가 이미 오픈소스로 존재해 구조를 참고/포크할 수 있음.
- 개인 MacBook에서 로컬 프로세스로 MCP 서버를 띄우고 Claude Desktop/Claude Code에 연결하는 구성은 이미 검증된 패턴(다른 MCP 서버들과 동일).

## 필요 도구
- **Jira Cloud API Token** — 무료 (Atlassian 계정에 API 토큰 발급, https://id.atlassian.com/manage-profile/security/api-tokens)
- **Python 3.11+ 또는 Node.js 20+** — 무료 (MCP SDK 지원 언어)
- **MCP Python SDK (`mcp`) 또는 TypeScript SDK (`@modelcontextprotocol/sdk`)** — 무료, 오픈소스
- **jira-python (`jira` 패키지) 또는 axios/requests** — 무료
- **Claude Desktop / Claude Code (MCP 클라이언트)** — 이미 사용 중이면 추가 비용 없음, Claude API 사용 시 토큰 비용 발생
- **(선택) SQLite** — 감사 이력 로컬 저장용, 무료
- **(선택) cron/launchd** — 주기적 감사 실행용, 무료 (macOS 기본 제공)

## 구현 단계
1. Jira Cloud 계정에서 API 토큰 발급 후, `.env` 파일에 `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` 저장 (git에 커밋되지 않도록 `.gitignore` 추가).
2. `Avtandil-abu/jira-ai-auditor` 리포지토리를 클론하거나, MCP Python SDK로 새 서버 프로젝트를 초기화 (`uv init` 또는 `npm init`).
3. Jira JQL 쿼리 3~5개를 정의: (a) 마감일 지난 미완료 이슈, (b) 담당자 없는 이슈, (c) 30일 이상 상태 변경 없는 이슈, (d) 스토리 포인트 없는 백로그 항목.
4. 각 JQL 쿼리를 호출하는 MCP tool(`get_stale_issues`, `get_unassigned_issues` 등)을 정의하고, 반환 데이터를 요약 통계(카운트, 평균 정체 일수 등)로 가공.
5. 로컬에서 `mcp dev` 또는 stdio 모드로 서버를 실행 테스트, Claude Desktop의 `claude_desktop_config.json`에 서버 등록 후 연결 확인.
6. Claude에게 "이번 주 프로젝트 건강 리포트 만들어줘"라고 요청해 MCP tool 호출 → 자연어 요약이 정상 작동하는지 검증.
7. (선택) launchd로 매주 월요일 오전 리포트를 생성해 Slack/이메일로 발송하는 스크립트 추가 (기존 `ai-info-radar`의 launchd 설정 패턴 재사용 가능).
8. 실제 팀/개인 Jira 프로젝트에 1주일간 적용해보고 JQL 기준값(며칠 이상 정체 시 "위험"으로 표시할지 등)을 조정.

## 예상 공수
- 기본 MCP 서버 구축 + 로컬 연동: 3~5시간
- JQL 규칙 튜닝 및 리포트 포맷 다듬기: 2~3시간
- launchd 자동화 + 알림 연동: 1~2시간
- **총 6~10시간, 난이도: 중** (Jira API 자체는 쉽지만 MCP 서버 프로토콜과 Claude 클라이언트 연동 디버깅에 시간이 걸릴 수 있음)

## 리스크/유의점
- Jira API 토큰이 로컬 `.env`에 평문 저장되므로 노트북 분실/유출 시 계정 보안 위험 — macOS Keychain 활용 고려.
- 팀 공용 Jira 프로젝트에 적용 시, 감사 리포트가 "감시" 도구로 오해받아 팀 반발을 일으킬 수 있음 — 도입 전 목적(업무 부담 경감)을 명확히 공유 필요.
- Jira Cloud API의 레이트 리밋(계정 등급별 상이)으로 대규모 프로젝트에서 잦은 폴링 시 429 에러 가능 — 캐싱 또는 폴링 주기 조정 필요.
- 참고 리포지토리가 HN 포인트 2점/커멘트 0개로 검증되지 않은 신생 프로젝트이므로, 코드 품질과 유지보수 여부를 직접 검토 후 포크할 것.

---
원본: https://github.com/Avtandil-abu/jira-ai-auditor
