# n8n으로 AI 챗봇 자동화 워크플로우 구축하기

## 개요
n8n은 오픈소스 워크플로우 자동화 도구로, 코드 작성 없이 노드 기반으로 AI 챗봇, 데이터 파이프라인, 알림 시스템 등을 구축할 수 있습니다. 이 항목은 n8n으로 AI 자동화 마스터클래스를 만든 경험을 다루며, 개인 MacBook 환경에서도 로컬 설치나 클라우드 호스팅을 통해 동일한 방식으로 실무형 AI 자동화(예: LLM 연동 챗봇, RSS/이메일 트리거 파이프라인)를 직접 구현할 수 있습니다.

## 구현 가능성 — 상
- n8n은 Docker/npm으로 macOS에 무료 설치 가능하며 공식 문서와 커뮤니티 템플릿이 풍부함.
- OpenAI/Anthropic API 노드가 기본 내장되어 있어 LLM 연동에 별도 개발 불필요.
- 기존 ai-info-radar 프로젝트의 SQLite 기반 수집·처리 파이프라인과 유사한 구조라 학습 곡선이 낮음.

## 필요 도구
- **n8n** — 오픈소스 자동화 플랫폼 (Self-hosted: 무료, n8n Cloud: 유료 $20/월~)
- **Docker Desktop for Mac** — n8n 컨테이너 실행 (무료)
- **Anthropic API (Claude)** 또는 **OpenAI API** — LLM 응답 생성 (사용량 기반 과금)
- **Ngrok** 또는 **Cloudflare Tunnel** — 로컬 n8n을 웹훅으로 외부 노출 (무료 티어 있음)
- **Telegram Bot API / Slack API** — 챗봇 인터페이스 (무료)
- **PostgreSQL 또는 SQLite** — 대화 기록/상태 저장 (무료)

## 구현 단계
1. `brew install --cask docker` 후 Docker Desktop 실행, `docker run -it --rm -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n` 명령으로 n8n 로컬 실행.
2. 브라우저에서 `http://localhost:5678` 접속하여 초기 계정 설정 및 owner 등록.
3. Telegram에서 BotFather로 봇 생성 후 토큰 발급, n8n에 Telegram Trigger 노드 추가하여 메시지 수신 연동.
4. Anthropic/OpenAI Credential을 n8n Credentials 메뉴에 등록하고, AI Agent(또는 OpenAI Chat) 노드를 추가해 시스템 프롬프트 설계.
5. Telegram Trigger → AI Agent 노드 → Telegram Send Message로 이어지는 기본 챗봇 워크플로우 연결 및 테스트.
6. 대화 컨텍스트 유지를 위해 n8n의 Memory 노드(Simple Memory 또는 Postgres Chat Memory) 추가.
7. `ngrok http 5678`로 로컬 서버를 외부에 노출하고, Telegram Webhook URL을 ngrok 주소로 등록해 실시간 응답 확인.
8. 필요 시 Google Sheets, Gmail, RSS Read 노드를 추가해 챗봇에 외부 데이터 조회/기록 기능 확장.
9. `launchd`(이미 프로젝트에 `launchd/` 디렉토리 존재)를 활용해 Docker/n8n이 macOS 부팅 시 자동 시작되도록 plist 등록.
10. 실제 사용 전 API 사용량 알림(예: Anthropic 대시보드 예산 알림) 설정.

## 예상 공수
- 기본 챗봇 워크플로우 구축: 약 3~5시간 (난이도: 하)
- 메모리/컨텍스트 유지 + 외부 데이터 연동 확장: 추가 4~6시간 (난이도: 중)
- 프로덕션 수준 안정화(웹훅 영구 호스팅, 에러 핸들링, 로깅): 추가 6~10시간 (난이도: 중~상)

## 리스크/유의점
- ngrok 무료 티어는 세션마다 URL이 바뀌므로 지속 운영 시 고정 도메인(Ngrok 유료 또는 자체 VPS) 필요.
- LLM API 키를 n8n Credentials에 저장 시 워크플로우 내보내기(export) 파일에 평문 노출될 수 있어 공유 전 반드시 확인.
- 로컬 MacBook에서 24/7 운영 시 절전 모드로 서비스가 중단될 수 있어, 장기 운영은 소형 VPS나 n8n Cloud 이전을 고려해야 함.
- 강의 자체는 힌디어(Hindi) 기반이라 언어 장벽이 있을 수 있으며, 실습은 n8n 공식 문서와 커뮤니티 템플릿으로 대체 가능.

---
원본: https://www.udemy.com/course/n8n-ai-automation-masterclass-build-ai-chatbots-hindi/?referralCode=4BD749DF5E397FC80B4C
