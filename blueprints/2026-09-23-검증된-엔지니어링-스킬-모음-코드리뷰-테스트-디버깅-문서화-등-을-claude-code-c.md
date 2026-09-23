# 검증된 엔지니어링 스킬 모음을 Claude Code에 설치해 코딩 에이전트 품질 끌어올리기

## 개요
addyosmani/agent-skills는 코드리뷰·테스트·디버깅·문서화 등 실전 검증된 스킬을 `~/.claude/skills/`에 폴더 복사만으로 설치해 사용하는 저장소다. 이를 도입하면 Claude Code로 진행하는 모든 프로젝트(현재 ai-info-radar 포함)에서 코드리뷰 품질과 일관성이 즉시 올라가고, 반복 지시 없이도 에이전트가 "실전 기준"으로 동작하게 되어 개인 작업 생산성뿐 아니라 향후 AI 자동화 컨설팅/외주 시 산출물 품질 근거로도 활용 가능하다.

## 구현 가능성 — 상
- 근거: 설치가 GitHub 저장소 clone 후 폴더 복사 수준(실현 5/5, 난이도 1/5)이며, Claude Code의 스킬 시스템(`~/.claude/skills/`)은 이미 사용 중인 기능이라 추가 학습 비용이 거의 없음. 스킬 자체가 마크다운+설명 기반이라 코드 수정 없이 즉시 적용 가능.

## 필요 도구
- **Claude Code** (이미 사용 중, 무료 기능인 스킬 시스템) — 비용 없음
- **git / GitHub CLI(gh)** — 저장소 clone용, 무료
- **addyosmani/agent-skills 저장소** — MIT 등 오픈소스 라이선스로 무료
- (선택) **Cursor / Codex** — 동일 스킬을 다른 에이전트 환경에도 이식 시, 각 도구의 규칙/커스텀 프롬프트 형식으로 변환 필요 (무료, 단 변환 작업 소요)

## 구현 단계
1. `git clone https://github.com/addyosmani/agent-skills.git /tmp/agent-skills` 로 저장소를 받는다.
2. README.md를 훑어 스킬 목록(예: code-review, testing, debugging, documentation 등)을 확인하고, 현재 하는 작업(AI 정보 레이더 대시보드 유지보수, Jev 관련 자동화, Claude Code 활용 수익화 프로젝트)과 겹치는 3~4개만 선정한다. 예: `code-review`, `testing`, `debugging` (+ 필요시 `documentation`).
3. 선정한 스킬 폴더만 `~/.claude/skills/`로 복사한다: `cp -r /tmp/agent-skills/skills/code-review ~/.claude/skills/` (README에 별도 설치 스크립트가 있으면 그것 사용).
4. Claude Code에서 `/context` 명령으로 토큰 사용량 증가분을 확인한다. 스킬 설명이 컨텍스트를 과도하게 차지하면 사용 빈도가 낮은 것부터 제거한다.
5. 새로 설치한 `code-review` 스킬을 이 저장소(`dashboard.html`, `collector.js` 등)에 대해 한 번 실행해보고, 기존 수동 리뷰 대비 발견되는 이슈의 질과 양을 비교한다.
6. 결과가 만족스러우면 나머지 선택 스킬(testing, debugging)도 실제 작업(예: collector.js 버그 수정, 신규 기능 테스트 작성)에 적용해 효과를 검증한다.
7. (수익화 관점) 효과가 검증되면 이 설치 과정과 전/후 비교(리뷰 발견 이슈 수, 수정 시간 단축 등)를 짧은 사례로 정리해, Claude Code 도입 컨설팅이나 "AI 코딩 에이전트 세팅 대행" 서비스의 데모/포트폴리오 자료로 재사용한다.

## 예상 공수
- 설치 및 1차 검증: 30분~1시간, 난이도 하
- 실제 프로젝트 적용 및 전/후 비교 정리: 추가 1~2시간, 난이도 하~중 (스킬을 실제 버그 수정에 써보고 결과를 기록하는 과정 포함)

## 리스크/유의점
- 스킬을 한 번에 다 설치하면 컨텍스트 토큰을 불필요하게 소모해 응답 속도/비용에 영향을 줄 수 있으니 3~4개로 제한할 것.
- 스킬 내용이 영어 기준으로 작성되어 있어 한국어 작업 맥락(커밋 메시지, 문서화 톤)과 약간의 스타일 불일치가 있을 수 있음 — 필요시 스킬 설명을 한국어로 일부 로컬라이즈.
- Cursor/Codex로 이식할 경우 스킬 포맷이 달라 그대로 복사가 안 되고 변환 작업이 필요함 — 우선 Claude Code에서만 검증 후 확장 여부 결정.
- 저장소가 활발히 업데이트 중(주간 +4,197 star)이므로 스킬 내용이 바뀔 수 있어, 설치 시점의 버전을 기록해두면 추후 효과 비교 시 기준점이 됨.

---
원본: https://github.com/addyosmani/agent-skills
