```markdown
# agency-agents로 Claude Code 서브에이전트 68개 한 번에 설치하기

## 쉽게 말하면
Claude Code에 "프론트엔드 개발자", "마케팅 담당자", "QA 테스터" 같은 이름표가 붙은 68명의 전문 조수를 한꺼번에 채용하는 것과 같아요. 한 번 설치해두면 이후에는 "Frontend Developer로 이 화면 고쳐줘"처럼 이름만 불러서 그 역할에 맞춰진 지시문으로 작업을 시킬 수 있습니다.

## 이걸로 할 수 있는 것
1. ig-dashboard 프로젝트에서 collector.js를 고칠 때 `devops-automator`를 불러 배포·자동화 관점으로 점검받기
2. 인스타 게시물 성과 데이터를 분석할 때 `data-analytics-reporter`를 불러 요약·리포트 초안 뽑기
3. 새 블루프린트 랜딩페이지나 카드뉴스 문구를 만들 때 `content-creator`나 `visual-storyteller`를 불러 톤앤매너 잡힌 초안 받기

## 개요
Claude Code의 서브에이전트 기능(.claude/agents/*.md)에 미리 만들어진 68개의 역할별 프롬프트를 한 번에 채워 넣어, 매번 "너는 ○○ 전문가야"라고 직접 프롬프트를 작성하지 않아도 되게 자동화하는 것입니다. 특히 1인 운영 중인 ai-info-radar/ig-dashboard 프로젝트처럼 여러 역할(개발·분석·마케팅·QA)을 혼자 오가야 하는 상황에서, 역할 전환 비용을 줄여주는 가치가 있습니다.

## 구현 가능성 — 중
GitHub 공개 저장소를 clone하고 파일을 `~/.claude/agents/`로 복사하는 작업 자체는 기술적으로 매우 단순해 "상"에 가깝지만, 실제 수익화·업무 효율로 이어지려면 68개 중 어떤 에이전트가 이 사용자의 실제 작업(ig-dashboard 유지보수, Jev 관련 콘텐츠 제작)에 쓸모 있는지 선별하고 품질을 검증하는 과정이 필요해 "중"으로 평가합니다. 게시물 자체도 "설치기는 댓글로만 배포"라고 밝혀 정보가 완전하지 않다는 점도 감안했습니다.

## 필요 도구
- GitHub (무료) — itallstartedwithaidea/agency-agents 저장소 clone
- Claude Code (구독 필요, 이미 사용 중) — 서브에이전트 기능 실행 환경
- 터미널/zsh (무료, macOS 기본 제공) — 파일 복사·설치 스크립트 실행
- (선택) 텍스트 에디터 — 설치 전 각 .md 파일 내용 검토용

## 구현 단계
1. 터미널에서 `git clone https://github.com/itallstartedwithaidea/agency-agents.git ~/Downloads/agency-agents`로 저장소를 받는다.
2. `~/Downloads/agency-agents/agents/` 폴더 구조를 열어 부서별(엔지니어링, 마케팅, 디자인, 테스팅, 서포트 등) 분류를 확인한다.
3. 각 .md 파일을 열어 frontmatter의 `name`과 본문 프롬프트 내용을 읽고, ig-dashboard/Jev 작업에 실제로 쓸 만한 5~10개(예: `data-analytics-reporter`, `devops-automator`, `content-creator`, `reality-checker`)를 골라 리스트업한다.
4. 선별한 파일만 `~/.claude/agents/`로 복사한다: `cp ~/Downloads/agency-agents/agents/<부서>/<선택한파일>.md ~/.claude/agents/`. 이미 동일한 이름의 파일이 있으면 덮어쓰지 말고 건너뛴다(게시물에서 언급한 "재실행 안전" 원칙 준수).
5. Claude Code를 재시작하거나 새 세션을 열어 `/agents` 또는 이름 호출("Frontend Developer로 이 컴포넌트 고쳐줘")로 정상 인식되는지 테스트한다.
6. ig-dashboard의 실제 파일(collector.js 등)을 대상으로 1~2개 에이전트를 시범 적용해보고, 응답 품질이 기존에 직접 쓰던 프롬프트보다 나은지 비교한다.
7. 쓸모없거나 응답 품질이 낮은 에이전트는 `~/.claude/agents/`에서 삭제하고, 유효한 것만 남겨 개인용 "정예 에이전트 세트"로 유지한다.

## 예상 공수
- 저장소 clone + 폴더 훑어보기: 15분 (난이도 하)
- 파일 선별 + 복사: 30분~1시간 (난이도 하, 68개 전체가 아니라 선별이라 시간 소요)
- 실사용 테스트 및 품질 검증: 1~2시간 (난이도 중, 실제 작업에 적용해보고 판단해야 함)
- 총합: 약 2~3시간, 난이도 중(하)

## 리스크/유의점
- 68개 중 다수가 이 사용자의 실제 업무(1인 프로젝트, Jev/ig-dashboard)와 무관한 대기업형 부서(공간컴퓨팅, 법무·컴플라이언스 등)라 그대로 전체 설치하면 오히려 이름 호출 시 혼란만 커질 수 있음 — 처음부터 선별 설치 권장.
- MIT 오픈소스이며 게시자와 무관한 프로젝트이므로, 프롬프트 품질이나 유지보수 여부가 보장되지 않음 — 실제 업무에 쓰기 전 각 프롬프트 내용을 직접 읽고 검증 필요.
- 설치기가 댓글로만 배포된다는 점에서, 공식 배포 채널 없이 개인이 배포하는 스크립트를 실행하게 되므로 스크립트 내용을 먼저 눈으로 확인한 뒤 실행할 것.
- Claude Code 서브에이전트 기능 자체는 무료지만 Claude Code 구독은 별도이므로, 이 자동화가 "수익 창출"로 이어지려면 실제 절감되는 작업 시간이 구독 비용을 상회하는지 확인 필요.
```

---
원본: https://www.instagram.com/p/DdgdIutjCQS/
