# Zigpoll MCP 서버로 AI 에이전트가 설문을 생성·발송·분석하게 하기

## 개요
Zigpoll이 제공하는 MCP(Model Context Protocol) 서버를 Claude Code나 다른 AI 에이전트에 연결하면, 자연어 명령만으로 설문 문항 설계, 발송 대상 지정, 응답 수집, 결과 분석까지 자동화할 수 있다. 반복적인 고객 피드백 수집·제품 만족도 조사·사내 설문 업무를 코드 작성 없이 대화형으로 처리할 수 있어, 마케팅/제품 담당자가 설문 도구를 직접 조작하는 시간을 크게 줄여준다.

## 구현 가능성 — 상
- MCP는 Claude Code, Claude Desktop 등에서 표준으로 지원하는 프로토콜이라 서버만 연결하면 별도 통합 코드가 거의 필요 없음
- Zigpoll이 이미 MCP 서버를 제공(Show HN 게시물 기준)하므로 자체 구현 없이 설정만으로 사용 가능
- 개인 MacBook에서 로컬 MCP 클라이언트(Claude Desktop/Claude Code)로 바로 테스트 가능해 인프라 부담이 없음
- 다만 Zigpoll 자체가 유료 SaaS일 가능성이 높고, MCP 서버의 인증/API 키 발급 절차와 무료 티어 범위를 사전 확인해야 함

## 필요 도구
- **Claude Desktop 또는 Claude Code** — MCP 클라이언트 (무료, Pro/Max 구독 시 더 원활)
- **Zigpoll 계정 및 API 키** — zigpoll.com 가입 필요 (유료, 무료 플랜 존재 여부 확인 필요)
- **Zigpoll MCP 서버 패키지** — 공식 GitHub/npm 배포본 확인 (무료 오픈소스로 추정, 확인 필요)
- **Node.js 또는 Python 런타임** — MCP 서버 로컬 실행용 (무료, macOS에 brew로 설치)
- **claude_desktop_config.json / .mcp.json** — MCP 서버 등록 설정 파일 (무료)

## 구현 단계
1. https://www.zigpoll.com 에서 계정 생성 후 대시보드에서 API 키(또는 MCP용 토큰) 발급
2. Zigpoll MCP 서버 저장소(GitHub) 또는 npm 패키지 확인 — `npx @zigpoll/mcp-server` 형태 실행 명령 존재 여부 문서에서 확인
3. macOS 터미널에서 Node.js 설치 확인: `node -v` (없으면 `brew install node`)
4. Claude Desktop 설정 파일(`~/Library/Application Support/Claude/claude_desktop_config.json`)에 Zigpoll MCP 서버 항목 추가:
   ```json
   {
     "mcpServers": {
       "zigpoll": {
         "command": "npx",
         "args": ["-y", "@zigpoll/mcp-server"],
         "env": { "ZIGPOLL_API_KEY": "발급받은키" }
       }
     }
   }
   ```
5. Claude Desktop 재시작 후 MCP 서버 연결 상태(초록 점/도구 목록 노출) 확인
6. 테스트로 "3문항짜리 제품 만족도 설문을 만들어줘"와 같이 자연어로 설문 생성 요청 → 생성된 설문 링크 확인
7. 소규모 테스트 그룹(팀원 2~3명)에게 링크 발송 후 응답 수집 흐름 검증
8. "응답 결과를 요약해줘" 요청으로 분석 기능 검증, 결과를 Slack/이메일로 공유하는 후속 자동화 여부 검토
9. 문제 없으면 반복 업무(예: 매주 사용자 피드백 설문)에 대해 launchd 스케줄러나 Claude Code `/loop`로 주기 자동화 고려

## 예상 공수
- 계정 생성 및 API 키 발급: 15분
- MCP 서버 설치·설정: 30분~1시간 (문서 미비 시 시행착오 추가 가능)
- 테스트 설문 생성·발송·분석 검증: 30분
- 총 예상: **1.5~2.5시간, 난이도 하~중** (MCP 자체는 쉬우나 Zigpoll 문서/요금제 확인에 변수 존재)

## 리스크/유의점
- Zigpoll 유료 플랜 전환 시 비용 발생 가능성 — 무료 티어의 설문 수/응답 수 제한 사전 확인 필요
- HN 포인트 2점, 댓글 0개로 신생/검증 안 된 서비스일 가능성 — MCP 서버의 안정성·유지보수 여부 불확실
- 설문 응답자 개인정보(이메일 등) 처리 시 데이터 보관 정책 확인 필요 (특히 사내/고객 대상 설문일 경우)
- API 키를 로컬 config 파일에 평문 저장하므로 macOS 파일 권한 관리 및 git 커밋 제외(.gitignore) 주의
- 자동화된 대량 설문 발송은 스팸으로 인식될 수 있어 수신자 동의(opt-in) 절차 확인 필요

---
원본: https://www.zigpoll.com
