# Gemini Live audio 실험 도구 구축 블루프린트

## 개요
Gemini 3.8 Live / Live Extended Thinking는 구글이 공개한 speech-to-speech(음성 입력→음성 출력) 모델로, WebSocket 기반 BidiGenerateContent API를 통해 실시간 음성 대화(끼어들기 포함)를 지원한다. 이를 활용해 브라우저에서 마이크 입력을 바로 Gemini와 음성으로 주고받는 개인용 프로토타입을 만들면, 음성 UX 실험이나 향후 제품에 붙일 음성 인터페이스의 타당성을 빠르게 검증할 수 있다.

## 구현 가능성 — 상
Simon Willison이 이미 라이브러리 없이 순수 JS + Web Audio API + WebSocket만으로 동작하는 참고 구현(`gemini-live.html`)을 공개했고, 필요한 것은 Gemini API 키뿐이다. 별도 서버나 빌드 과정 없이 정적 HTML 파일 하나를 브라우저에서 열기만 하면 되므로 macOS 로컬 환경 도입 장벽이 매우 낮다.

## 필요 도구
- **Gemini API 키** — https://aistudio.google.com 에서 발급 (무료 티어 있음, Live API 사용량은 과금 대상일 수 있어 확인 필요)
- **참고 구현 코드** — https://github.com/simonw/tools/blob/main/gemini-live.html (무료, OSS, 그대로 복사해서 사용 가능)
- 최신 Chrome/Safari 등 Web Audio API + WebSocket을 지원하는 브라우저 (무료, 기본 제공)
- (선택) 로컬 정적 서버 — `python3 -m http.server` 또는 VS Code Live Server (무료, 마이크 권한이 file:// 에서 막힐 경우 필요)
- (선택) 헤드폰/이어폰 — 에코 방지용 (하드웨어 보유 시 무료)

## 구현 단계
1. https://aistudio.google.com 에서 구글 계정으로 로그인 후 API 키를 발급받는다. 결제 계정 연결 여부와 Live API 무료 한도를 콘솔에서 확인한다.
2. `gemini-live.html` 파일을 다운로드한다: `curl -O https://raw.githubusercontent.com/simonw/tools/main/gemini-live.html`
3. 로컬 프로젝트 폴더(예: `~/experiments/gemini-live/`)에 파일을 두고, `python3 -m http.server 8000`으로 해당 폴더에서 정적 서버를 띄운다 (file:// 직접 열기 시 마이크 권한이 막히면 이 단계가 필요).
4. 브라우저에서 `http://localhost:8000/gemini-live.html` 접속 후, 발급받은 API 키를 UI의 키 입력란에 붙여넣는다.
5. 모델(Gemini 3.8 Live 또는 Live Extended Thinking)과 음성 프리셋을 선택하고, 필요하면 시스템 프롬프트를 입력한다.
6. "Start session" 클릭 → 브라우저 마이크 권한 요청을 허용한다. 헤드폰 사용을 권장 (스피커 사용 시 에코로 모델이 자기 음성을 다시 인식할 수 있음).
7. 음성으로 대화하며 말하는 중간에 끼어들기(interrupt)가 정상 동작하는지, 텍스트 입력창으로 메시지를 보냈을 때도 응답이 끊기는지 테스트한다.
8. 대화 내용을 "Download transcript"로 저장해 두고, 이후 어떤 용도(예: 육아 정보 음성 인터페이스, 고객 문의 음성봇 프로토타입)에 적용 가능할지 메모한다.
9. 코드를 직접 수정해가며 (예: 시스템 프롬프트 고정, UI 커스터마이징, 특정 도메인 지식 주입) 팀/제품 맥락에 맞는 PoC로 발전시킨다.

## 예상 공수
- API 키 발급 + 파일 다운로드 + 첫 실행: 15~20분
- 음성 대화 테스트 및 끼어들기/동작 확인: 20~30분
- 코드 커스터마이징(시스템 프롬프트, UI 조정 등)까지 포함 시: 추가 1~2시간
- 난이도: **하** — 기존 구현을 그대로 실행하는 수준이면 코딩 불필요, 커스터마이징 시에도 순수 JS 파일 하나만 수정하면 되어 진입장벽 낮음

## 리스크/유의점
- **API 키가 클라이언트 사이드 HTML에 그대로 노출**되는 구조이므로, 이 파일을 로컬에서만 쓰고 공개 웹에 그대로 배포하지 않도록 주의. 배포하려면 키를 서버 프록시 뒤로 숨기는 작업이 별도로 필요.
- Live API는 실시간 스트리밍 특성상 **일반 텍스트 API보다 과금 단가가 높을 수 있어**, 실험 전 구글의 최신 Live API 가격 정책을 콘솔에서 직접 확인할 것.
- WebSocket 엔드포인트(`wss://generativelanguage.googleapis.com/...`)와 모델 이름은 구글 측에서 변경될 수 있으므로, 참고 구현이 오래되면 최신 공식 문서(https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket)와 대조해 업데이트가 필요할 수 있음.
- 마이크로 수집되는 음성 데이터가 구글 서버로 전송되므로, 민감한 대화 내용(개인정보, 미공개 제품 정보 등)으로 테스트하지 않도록 주의.

---
원본: https://simonwillison.net/2026/Sep/15/gemini-live/

---
원본: https://simonwillison.net/2026/Sep/15/gemini-live/
