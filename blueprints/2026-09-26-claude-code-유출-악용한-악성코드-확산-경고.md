# Claude Code 공급망 보안 스캐너로 개발자 대상 유료 진단 서비스 만들기

## 쉽게 말하면
누군가 Claude Code 설정 파일이나 플러그인에 악성 코드를 몰래 심어서 퍼뜨리다 걸린 사건입니다. 마치 "믿을 만한 앱스토어인 줄 알고 설치했더니 알고 보니 가짜 업데이트가 껴 있던 것"과 비슷합니다. 이걸 계기로, 다른 개발자들의 Claude Code 환경(설정·훅·MCP 서버·플러그인)에 위험한 설정이 숨어 있는지 자동으로 검사해주는 도구를 만들어 팔 수 있습니다.

## 이걸로 할 수 있는 것
1. 내 맥북에서 먼저 나의 `.claude/settings.json`, 훅, MCP 서버 목록을 스캔해 위험한 권한(예: `--no-verify`, 임의 URL 접근, 쉘 명령 자동 승인)이 있는지 점검한다.
2. 프리랜서·에이전시로서 고객사 개발팀의 Claude Code 설정을 원격으로 감사(audit)해주고 리포트를 판매하는 1회성 유료 서비스를 만든다.
3. "Claude Code 보안 체크리스트" 자동 스캔 스크립트를 깃허브에 공개하고, 유료 버전(고급 룰셋 + 슬랙 알림 연동)을 구독형으로 판매한다.

## 개요
Claude Code, MCP 서버, 플러그인 생태계가 빠르게 커지면서 악성 설정·훅·서드파티 플러그인을 통한 공급망 공격 위험이 실제 뉴스로 확인됐습니다. 이 틈새를 파고들어, 개발자와 팀의 Claude Code 환경을 스캔해 위험 신호(과도한 자동 승인 권한, 알 수 없는 MCP 서버, 의심스러운 훅 스크립트 등)를 찾아내는 자동화 도구를 만들면, 개인 보안 점검부터 팀 단위 유료 감사까지 확장 가능한 수익 모델이 됩니다.

## 구현 가능성
**상** — 근거: Claude Code 설정 파일(`settings.json`, `.claude/` 디렉토리, hooks, MCP 서버 목록)은 전부 로컬 파일이라 파싱이 쉽고, 이미 `update-config` 스킬처럼 관련 룰을 다루는 기반이 있습니다. 정적 분석(JSON 스키마 검사 + 패턴 매칭) 수준이면 개인 맥북에서 며칠 안에 프로토타입이 가능합니다.

## 필요 도구
- **Claude Code / Claude API** — 스캔 결과 요약, 위험도 설명 자동 생성 (유료, 이미 보유 중인 구독으로 가능)
- **Python 또는 Node.js** — 스캐너 스크립트 작성 (무료)
- **jsonschema / ajv** — settings.json 구조 검증 라이브러리 (무료, 오픈소스)
- **GitHub Actions** — 고객 레포에 CI로 자동 스캔 붙이는 용도 (무료 티어 존재, 사용량 초과 시 유료)
- **Notion 또는 Google Docs API** — 감사 리포트 자동 생성·전달 (무료 또는 저가)
- **Stripe / Gumroad** — 유료 스캔 리포트·구독 결제 수단 (거래 수수료 있음)
- **Slack/Webhook API** — 위험 발견 시 알림 (무료)

## 구현 단계
1. 맥북에 있는 `~/.claude/settings.json`, `.claude/settings.local.json`, 프로젝트별 훅 설정을 모아 구조를 파악한다.
2. "위험 패턴 목록"을 정의한다 — 예: `--no-verify` 사용, `permissions.allow`에 `*` 와일드카드, 출처 불명 MCP 서버 URL, base64로 인코딩된 훅 명령어 등. 이번 IT조선 기사 및 관련 공급망 공격 사례를 참고해 룰을 5~10개 작성한다.
3. Python 스크립트로 위 설정 파일들을 파싱하고 룰과 대조해 위험도 점수(상/중/하)를 매기는 `scan.py` 프로토타입을 만든다.
4. Claude API를 호출해, 발견된 위험 항목마다 "왜 위험한지, 어떻게 고치는지"를 자연어 리포트로 자동 생성하도록 연결한다.
5. 스캔 결과를 PDF/Notion 리포트 형태로 예쁘게 정리하는 템플릿을 만든다(첫 고객 확보용 샘플 리포트).
6. 무료 버전(로컬 CLI, 기본 룰셋)을 GitHub에 공개해 신뢰와 트래픽을 확보하고, 유료 버전(팀 대시보드, CI 연동, 커스텀 룰, 슬랙 알림)은 Gumroad/Stripe로 월 구독 또는 1회 감사비를 받는다.
7. 개발자 커뮤니티(디스코드, 트위터/X, 국내 개발자 카페)에 "Claude Code 보안 자가진단" 무료 체크로 홍보하고, 팀 단위 유료 감사로 전환시킨다.

## 예상 공수
- 프로토타입(로컬 스캐너 + 기본 룰 5개): 6~10시간, 난이도 중
- 리포트 자동 생성 + Claude API 연동: 4~6시간, 난이도 중
- 결제·배포·공개 CLI 패키징: 6~8시간, 난이도 중~상
- 총합 약 16~24시간(1~2주 저녁 작업 분량)으로 최소 판매 가능 버전(MVP) 완성 가능

## 리스크/유의점
- 오탐(false positive)이 많으면 신뢰를 잃으므로 룰셋을 보수적으로 시작하고 점진적으로 확장해야 한다.
- 고객사 설정 파일을 감사할 경우 민감 정보(내부 API 키, 서버 주소)가 포함될 수 있으므로 데이터 취급·삭제 정책을 명확히 하고 계약서에 명시해야 한다.
- "보안 진단"을 표방하는 만큼 실제 취약점을 놓치거나 과장하면 평판 리스크가 크므로, 확신 없는 항목은 "주의 필요"로만 표시하고 단정적 주장은 피해야 한다.
- Claude Code나 MCP 생태계의 설정 스키마가 업데이트되면 룰셋도 계속 유지보수해야 하는 지속 비용이 발생한다.

---
원본: https://news.google.com/rss/articles/CBMicEFVX3lxTFA3R0NCSk90aEhucWNmcHZJTHNEY2d1M2lUNTRidk1Ldjlqamc2WEttT3J6V2Y5dzNSa0o2TjdmRy1pZkxWc0lVZUpQZ2YybHJfQm9Jd2RwYndDa2J5enI5M1puR2RnWFhrRUhmRUFnbFTSAXRBVV95cUxNMnFlNzJjYndxaVRZcDRuZGRyQlFXZ2hZdXh6UVAtX3N6RnhPMmx4SXVlY1dNVzFWUTM4Vy1OckVHUTZxMVVWVmZVVmYtQ2NkelhqLW5yajNseXcxb0loZmRkcldMQnYtSEtYUHZLOGdDbm1jQg?oc=5
