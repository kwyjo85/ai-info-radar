#어떤 에이전트든 샌드박스·브라우저·GitHub 접근권을 갖게 하는 MCP 서버 구축

## 개요
Upstash가 공개한 MCP(Model Context Protocol) 서버는 Claude, Cursor 등 어떤 AI 에이전트에도 코드 실행 샌드박스, 헤드리스 브라우저, GitHub API 접근을 표준화된 방식으로 연결해준다. 이를 자체 인프라(Upstash Redis/QStash 또는 대체 오픈소스 조합)로 재현하면, 개인 MacBook에서도 "요청 → 코드 생성 → 샌드박스 실행/검증 → 브라우저로 결과 확인 → GitHub PR 생성"까지 이어지는 자율형 코드 팩토리 파이프라인을 로컬에서 운용할 수 있다.

## 구현 가능성 — 중
MCP 프로토콜 자체는 표준화되어 있고 Python/TypeScript SDK가 성숙해 서버 골격 작성은 어렵지 않다. 다만 (1) 안전한 코드 샌드박스(도커 격리) 구성, (2) 헤드리스 브라우저 제어(Playwright MCP 등 기존 도구 재사용 가능), (3) GitHub 토큰 권한 설계 및 액션 승인 흐름을 직접 설계해야 하므로 순수 "설정만 하면 끝"은 아니다. 기존 오픈소스 MCP 서버(Playwright MCP, GitHub MCP, 코드 샌드박스 MCP)를 조합하면 난이도가 크게 낮아진다.

## 필요 도구
- **Claude Code / Claude Desktop** — MCP 클라이언트 역할 (무료 티어 가능, Pro/Max 권장)
- **Docker Desktop for Mac** — 코드 실행 격리 샌드박스 (무료)
- **Playwright MCP server** (`@modelcontextprotocol/server-playwright` 또는 마이크로소프트 공식) — 브라우저 제어 (무료, 오픈소스)
- **GitHub MCP server** (`@modelcontextprotocol/server-github`) — 이슈/PR/커밋 관리 (무료, GitHub PAT 필요)
- **Node.js 20+ / TypeScript** 또는 **Python 3.11+** — MCP 서버 커스텀 로직 작성 (무료)
- **Upstash Redis / QStash** (선택) — 작업 큐·상태 저장, 서버리스 실행 이력 관리 (무료 티어 있음, 초과 시 종량 과금)
- **GitHub Personal Access Token (Fine-grained)** — 레포별 최소 권한 발급 (무료)
- **Sandbox 런타임** — `e2b` SDK 또는 자체 Docker 컨테이너 (`docker run --rm --network=none`) (e2b는 유료 API, Docker는 무료)

## 구현 단계
1. Docker Desktop 설치 및 `docker run --rm -it python:3.11-slim` 등으로 격리 컨테이너에서 코드 실행이 가능한지 사전 확인.
2. `npx @modelcontextprotocol/create-server my-sandbox-mcp`로 MCP 서버 프로젝트 스캐폴딩 생성.
3. 샌드박스 실행 툴(`run_code`) 구현: 요청받은 코드를 `docker run --rm --network=none -v $(pwd)/workspace:/workspace python:3.11-slim python /workspace/script.py` 형태로 실행하고 stdout/stderr를 반환하는 함수 작성. 타임아웃(예: 30초)과 리소스 제한(`--memory=512m --cpus=1`) 필수 적용.
4. Playwright MCP 서버를 별도 프로세스로 설치(`npm install -g @playwright/mcp` 후 `npx playwright install chromium`)하고 Claude Code의 `.mcp.json` 또는 `claude mcp add` 명령으로 등록.
5. GitHub MCP 서버 설치 후 fine-grained PAT(레포 읽기/쓰기, PR 생성 권한만) 발급하여 환경변수로 주입, `claude mcp add github`로 등록.
6. 세 서버를 하나의 `.mcp.json`(프로젝트 루트)에 통합 등록:
   ```json
   {
     "mcpServers": {
       "sandbox": { "command": "node", "args": ["my-sandbox-mcp/dist/index.js"] },
       "browser": { "command": "npx", "args": ["@playwright/mcp"] },
       "github": { "command": "npx", "args": ["@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "..."} }
     }
   }
   ```
7. Claude Code에서 "이 버그를 고치고, 샌드박스에서 테스트를 돌리고, 브라우저로 UI를 확인한 뒤 PR을 올려줘" 같은 실제 태스크로 end-to-end 테스트.
8. 위험한 도구 호출(파일 삭제, `git push`, PR 생성 등)에 대해 permission 모드를 `--permission-mode ask`로 설정해 매번 승인받도록 안전장치 마련.
9. (선택) Upstash QStash로 야간 배치 작업(정기 코드 검증, 의존성 업데이트 PR 자동 생성)을 스케줄링.

## 예상 공수
- 기본 MCP 서버 3종 설치·연동: 3~4시간 (난이도: 하)
- 커스텀 샌드박스 도구 작성 및 리소스 제한 튜닝: 4~6시간 (난이도: 중)
- 권한/승인 흐름 및 보안 검증(네트워크 차단, 토큰 스코프 최소화): 2~3시간 (난이도: 중)
- 전체 합산: 약 1~2일(집중 작업 기준)

## 리스크/유의점
- 샌드박스 격리가 허술하면(`--network=none` 누락 등) 에이전트가 생성한 코드가 로컬 파일시스템이나 네트워크에 접근할 위험이 있음 — 반드시 컨테이너 네트워크/볼륨 마운트를 최소화.
- GitHub PAT은 반드시 fine-grained 토큰으로 발급하고 대상 레포·권한을 제한할 것. 광범위한 classic PAT 사용 시 에이전트 오작동으로 다른 레포에 영향을 줄 수 있음.
- 자동 PR 생성/머지 기능은 사람 승인 단계(`ask` 모드) 없이는 절대 활성화하지 말 것 — 의도치 않은 코드 배포 위험.
- Playwright 브라우저 제어는 실제 웹사이트 상태를 변경할 수 있으므로(폼 제출 등) 테스트 대상 사이트를 로컬/스테이징으로 한정 권장.
- MacBook 로컬 자원(CPU/메모리)으로 다중 컨테이너 실행 시 배터리·발열 부담이 있으니 동시 실행 수를 제한.

---
원본: https://upstash.com/blog/turn-any-agent-into-a-code-factory-with-an-mcp
