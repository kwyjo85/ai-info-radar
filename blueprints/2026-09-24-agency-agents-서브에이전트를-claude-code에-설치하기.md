# agency-agents 서브에이전트를 Claude Code에 설치하기

## 쉽게 말하면
Claude Code에 "전문 분야별 AI 직원 명함"을 미리 만들어 꽂아두는 것과 비슷해요. 원래는 매번 "너는 프론트엔드 개발자야, 이렇게 검토해줘"라고 설명해야 하는데, 이 명함(서브에이전트 정의 파일)을 한 번 꽂아두면 그냥 "Frontend Developer 에이전트로 봐줘"라고 이름만 불러도 그 역할에 맞게 대답합니다.

## 이걸로 할 수 있는 것
1. Jev나 다른 프로젝트의 UI 컴포넌트를 수정할 때 "UI Designer 에이전트로 이 화면 디자인 검토해줘"라고 불러서 바로 피드백을 받는다.
2. 클라이언트 납품용 코드를 배포하기 전에 "Security Engineer 에이전트로 이 API 취약점 점검해줘"라고 시켜 무료 보안 리뷰를 받는다.
3. 수익화용 콘텐츠(블로그·인스타 카피)를 쓸 때 "Content Creator 에이전트로 이 글 다듬어줘"라고 호출해 매번 프롬프트를 새로 짜지 않고도 일관된 품질을 얻는다.

## 개요
GitHub 오픈소스(agency-agents)에 있는 부서별 서브에이전트 정의 파일(.md)을 `~/.claude/agents/` 폴더에 복사하는 것만으로, Claude Code가 이름으로 호출 가능한 역할(프론트엔드, 보안, 마케팅, 디자인 등)을 갖추게 됩니다. 매번 역할 설명 프롬프트를 반복 작성할 필요가 없어져 외주·클라이언트 작업 시 속도와 품질이 올라가고, 이는 곧 Claude Code로 처리 가능한 작업 범위(=받을 수 있는 일)가 넓어진다는 뜻입니다.

## 구현 가능성: 상
- 저장소가 실제 공개(MIT 라이선스)돼 있고 설치 방식이 단순 파일 복사 수준으로 확인됨.
- Claude Code의 서브에이전트 기능이 `.md` 파일을 `~/.claude/agents/`에서 읽어오는 방식과 정확히 호환됨.
- 별도 서버·API 키·빌드 과정 없이 로컬 파일 시스템 작업만으로 완결됨.

## 필요 도구
- Claude Code (구독 필요, 유료) — 이미 사용 중
- `git` — 저장소 clone용 (무료, macOS 기본 내장 또는 Xcode CLT)
- GitHub 저장소: `msitarzewski/agency-agents` (원조, 스타 다수 — 추천) 또는 `itallstartedwithaidea/agency-agents` (무료, MIT)
- 터미널(zsh) — 파일 복사·개수 비교 스크립트 실행용 (무료, macOS 기본)

## 구현 단계
1. 작업용 임시 폴더에 저장소를 clone한다: `git clone https://github.com/msitarzewski/agency-agents.git ~/tmp/agency-agents`
2. 설치 전 기존 에이전트 개수를 기록한다: `find ~/.claude/agents -name "*.md" | wc -l`
3. README에 설치 스크립트(`./scripts/install.sh --tool claude-code`)가 있으면 그대로 실행하고, 없으면 부서 폴더 중 실제로 쓸 것만 선택 복사한다: 예) `cp ~/tmp/agency-agents/engineering/{frontend-developer,security-engineer,ai-engineer}.md ~/.claude/agents/`
4. 68개 전부가 아니라 지금 하는 일(엔지니어링·마케팅 콘텐츠·디자인 검토)에 맞는 5~10개만 우선 설치한다.
5. 설치 후 개수를 다시 세어 정확히 늘어난 만큼만 복사됐는지 확인한다: `find ~/.claude/agents -name "*.md" | wc -l`
6. 동일 이름이 이미 있으면 덮어쓰지 않도록 `cp -n` 옵션을 사용하거나, 복사 전 `ls ~/.claude/agents/`로 중복 이름을 미리 확인한다.
7. 실제 작업 중인 프로젝트(예: ig-dashboard의 `collector.js` 개선, `dashboard.html` UI 수정)에서 "Frontend Developer 에이전트로 이 컴포넌트 검토해줘"처럼 이름을 불러 시험 적용하고, 결과물 품질이 기대에 미치는지 확인한다.
8. 클라이언트/외주 작업 유형별로 자주 쓰는 에이전트 조합을 메모해두고, 이후 신규 프로젝트 시작 시 그 조합만 빠르게 재설치하는 나만의 체크리스트를 만든다.

## 예상 공수
- 총 30분~1시간 (난이도: 하)
- clone 및 선택 복사: 10분
- 설치 전후 개수 검증: 5분
- 실제 프로젝트에서 3~4개 에이전트 시험 호출 및 결과 확인: 20~40분

## 리스크/유의점
- `itallstartedwithaidea/agency-agents`는 스타 수가 적은 소규모 포크이므로, 실제로는 더 널리 검증된 `msitarzewski/agency-agents`(원조, 15만+ 스타)를 쓰는 것이 안정성 면에서 낫다.
- 68개를 전부 설치하면 Claude Code가 매 요청마다 에이전트 목록을 참고하는 부담이 커지고, 실제로 안 쓰는 정의가 컨텍스트만 차지할 수 있으므로 실사용 부서 몇 개로 제한할 것.
- 서브에이전트 정의는 어디까지나 "역할 프롬프트"이지 실제 전문가 검증을 대체하지 않으므로, 보안·법률 관련 결과물은 반드시 별도 확인 절차를 거칠 것.
- agency-agents는 제3자가 만든 MIT 오픈소스이며 Anthropic이나 Claude Code 공식 제공 기능이 아니므로, 향후 Claude Code 서브에이전트 스펙이 바뀌면 정의 파일 포맷이 깨질 수 있다.

---
원본: https://www.instagram.com/p/DdgaTgwCB0z/
