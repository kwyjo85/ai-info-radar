# Claude Code 작업을 Notion에 자동 기록

## 쉽게 말하면
클로드코드가 작업을 끝낼 때마다(Stop 이벤트) "방금 뭘 했는지"를 자동으로 노션 페이지 한 줄로 적어주는 것입니다. 회의가 끝날 때마다 비서가 알아서 회의록 한 줄을 노트에 남겨주는 것과 같아서, 나중에 "그때 뭐 했더라"를 찾아 헤맬 필요가 없어집니다.

## 이걸로 할 수 있는 것
1. 여러 고객사의 자동화·Jev 관련 작업을 동시에 진행할 때, 세션별 작업 로그가 노션에 자동으로 쌓여 인보이스·작업 보고서를 쓸 때 그대로 근거 자료로 쓴다.
2. ai-info-radar처럼 반복적으로 collector.js 등을 고치는 세션에서 무엇을 왜 고쳤는지 자동 기록돼, 다음 세션이나 다른 서브에이전트가 맥락을 빠르게 파악한다.
3. Claude Code로 유료 자동화를 파는 1인 사업자 입장에서 "작업 이력 자동 기록"을 클라이언트에게 투명성 증거로 제공하거나, 이 훅 셋업 자체를 다른 Claude Code 사용자에게 파는 미니 상품으로 만든다.

## 개요
Stop hook(응답 완료 시 자동 실행) + 파이썬 스크립트 + Notion API를 연결해, 매 작업이 끝날 때마다 요약을 Notion DB에 자동 적재하는 것입니다. 수익화 관점에서는 별도 노무 없이 작업 로그·증빙이 자동 생성돼 시간당 과금 근거를 만들거나, 이 훅 구축 자체를 셋업 서비스로 판매할 수 있습니다.

## 구현 가능성
**상** — Claude Code hooks는 공식 기능(`settings.json`의 `hooks.Stop`)이고, Notion API도 공개 문서와 무료 토큰 발급 절차가 확립되어 있음. 스크립트는 Claude Code에게 직접 작성을 요청하면 되므로 외부 코드 신뢰 없이도 처음부터 구현 가능.

## 필요 도구
- Claude Code CLI (이미 사용 중, 무료 설치·유료는 Anthropic 사용량 과금)
- `~/.claude/settings.json` hooks 설정 (Claude Code 내장, 무료)
- Python 3 (무료)
- Notion 계정 + Integration 토큰 (app.notion.com/developers/connections, 무료)
- `notion-client` 또는 `requests` 파이썬 패키지 (무료, pip)
- (대안) Notion 대신 이 저장소의 `data.js`/JSON에 직접 기록 — 별도 서비스 불필요, 무료

## 구현 단계
1. Notion에서 새 데이터베이스를 만든다 (컬럼 예: 날짜, 프로젝트, 요약, 태그).
2. app.notion.com/developers/connections 에서 새 Integration을 생성해 토큰을 발급받고, 방금 만든 DB에 해당 Integration을 Share로 연결한다.
3. 발급받은 토큰을 `~/.claude/notion_token.txt` 등 git 추적 밖 위치에 저장한다 (repo `.gitignore` 확인 필수).
4. `~/.claude/settings.json`에 `hooks.Stop`을 등록하되, 먼저 `echo "hook fired" >> ~/hook_test.log` 같은 테스트 명령으로 응답 종료 시 훅이 실제 실행되는지 확인한다.
5. Claude Code에 "Stop hook에서 마지막 대화 요약을 만들어 Notion DB에 새 row로 추가하는 파이썬 스크립트를 작성해줘, 토큰은 파일에서 읽고 DB ID는 환경변수로 받게 해줘"라고 요청해 스크립트를 생성한다.
6. `settings.json`의 `hooks.Stop` command를 방금 만든 스크립트 실행으로 교체하고, 실제 작업 세션에서 Notion에 기록되는지 검증한다.
7. (선택, ai-info-radar 특화) Notion 대신 이 프로젝트의 `data.js`/JSON에 "작업 로그" 필드를 추가해 같은 훅이 로컬 파일에 기록하도록 변형하면, 대시보드에서 바로 조회할 수 있다.
8. 여러 프로젝트·클라이언트를 구분해야 한다면, 훅 스크립트가 현재 작업 디렉터리(cwd)를 읽어 Notion의 "프로젝트" 속성에 자동 분류하도록 확장한다.

## 예상 공수
- Notion DB·토큰 설정: 20~30분
- Stop hook 테스트(echo)로 동작 확인: 10분
- Claude Code로 스크립트 생성 및 디버깅: 1~2시간
- 대시보드 연동 등 확장(선택): 추가 1~2시간
- 난이도: **중** (설정 자체는 쉬우나 hook payload 파싱과 토큰 보안 처리에 약간의 디버깅 필요)

## 리스크/유의점
- 토큰을 실수로 커밋하면 노션 워크스페이스 전체가 노출될 수 있음 — 반드시 git 추적 밖에 보관하고 `.gitignore`를 확인할 것.
- Stop hook은 세션 종료가 아니라 "매 응답 완료"마다 실행되므로, 대화가 길어지면 로그가 과도하게 쌓일 수 있음 — 파일 수정이 있었을 때만 기록하는 등 조건이 필요.
- 영상 속 코드는 고정 댓글 링크로만 제공되어 원본을 직접 검증할 수 없음 — Claude Code에 직접 짜달라고 해서 로직을 스스로 확인하고 쓸 것.
- 클라이언트 작업 로그를 자동 기록·공유할 경우 코드 스니펫·고객명 같은 민감정보가 노션에 노출될 수 있어, 요약 프롬프트에 마스킹 규칙을 넣을 필요가 있음.

---
원본: https://www.youtube.com/watch?v=B2cDUYqmP6I

---
원본: https://www.youtube.com/watch?v=B2cDUYqmP6I
