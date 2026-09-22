# 데스크톱 AI 에이전트 센터 – 핫키로 로컬 AI 자동화 구축

## 개요
ChatGPT, Gemini, Perplexity 같은 웹 기반 AI 인터페이스를 매번 브라우저 탭 전환·복붙 없이 전역 핫키로 즉시 호출하는 로컬 게이트웨이를 구축한다. 클립보드 내용이나 선택 텍스트를 트리거로 AI에 전달하고 결과를 다시 데스크톱 워크플로우(메모 앱, 에디터, 문서 등)로 되돌리는 반복 작업을 자동화하여, 하루 수십 번의 "복사 → 탭 전환 → 붙여넣기 → 결과 복사 → 돌아오기" 과정을 단축한다.

## 구현 가능성 — 중
근거: 오픈소스 저장소(WellWells/desktop-agent-center)가 이미 존재하나 스타/문서화 수준이 낮고(포인트 1점) 유지보수 상태가 불확실하다. 유사 컨셉(Raycast, Alfred 워크플로우, AutoHotkey/Hammerspoon 스크립트)을 직접 조합해도 동일 기능 구현이 가능해 위험 부담이 낮다. 다만 ChatGPT/Gemini/Perplexity의 "웹 인터페이스 자동화"는 공식 API가 아닌 브라우저 자동화(스크래핑/자동입력) 방식일 가능성이 높아 각 서비스 이용약관 위반 소지 및 UI 변경에 따른 취약성이 존재한다.

## 필요 도구
- **macOS 자동화 프레임워크**: Hammerspoon (무료, 오픈소스) 또는 Keyboard Maestro (유료, $36 1회성)
- **핫키 바인딩**: skhd 또는 Hammerspoon 내장 hotkey API (무료)
- **AI API 연동 (권장, 웹 자동화 대체)**:
  - Anthropic API (Claude, claude-sonnet-5) — 종량제 과금
  - OpenAI API (GPT) — 종량제 과금
  - Google Gemini API — 무료 티어 존재, 초과 시 종량제
  - Perplexity API — 종량제
- **클립보드/텍스트 캡처**: macOS `pbpaste`/`pbcopy`, 또는 Hammerspoon `hs.pasteboard`
- **로컬 실행 스크립트**: Python 3 + `requests`/`anthropic` SDK, 또는 Node.js (무료)
- **선택: Desktop Agent Center 원본 저장소** (무료, 단 유지보수 리스크 있음, 코드 리뷰 필요)
- **선택: 백그라운드 상시 구동**: launchd plist (macOS 기본 제공, 무료)

## 구현 단계
1. Desktop Agent Center 저장소를 클론해 코드 구조와 라이선스를 검토한다 (`git clone https://github.com/WellWells/desktop-agent-center`). 웹 UI 자동화 방식(Playwright/Selenium 기반인지) 확인.
2. 웹 UI 자동화가 아닌 **공식 API 방식으로 재구현**하기로 결정한다(약관 위반·깨짐 리스크 회피). Anthropic/OpenAI/Gemini API 키를 발급받아 `.env`에 저장.
3. Python 스크립트(`agent_hotkey.py`) 작성: 선택된 텍스트 또는 클립보드 내용을 읽어 지정 모델 API에 요청을 보내고 응답을 받는 함수 구현.
4. Hammerspoon 설치(`brew install hammerspoon`) 후 `~/.hammerspoon/init.lua`에 전역 핫키(예: `Cmd+Shift+A`) 바인딩, 트리거 시 클립보드 내용을 위 스크립트로 전달.
5. 스크립트 결과를 macOS 알림(`hs.notify`)이나 별도 팝업 창(`hs.webview`)으로 표시하고, 자동으로 클립보드에 결과를 복사(`pbcopy`)해 바로 붙여넣기 가능하게 처리.
6. 용도별 프리셋 추가(예: `Cmd+Shift+S` 요약, `Cmd+Shift+T` 번역, `Cmd+Shift+E` 영문 교정) — 각 프리셋마다 다른 프롬프트 템플릿을 스크립트 인자로 분기.
7. launchd로 스크립트/Hammerspoon 상시 구동 설정(로그인 시 자동 실행)하고, API 키는 macOS Keychain 또는 `.env` + `.gitignore`로 보호.
8. 1주일 실사용하며 응답 속도, 자주 쓰는 프리셋, 오류 상황(네트워크 끊김, API 한도 초과)을 기록하고 스크립트 보완.

## 예상 공수
- 총 6~10시간 (Hammerspoon 설정 1~2시간, API 연동 스크립트 2~3시간, 프리셋/UX 다듬기 2~3시간, 안정화 테스트 2시간)
- 난이도: 중 (쉘/파이썬 스크립팅 및 macOS 자동화 도구 경험이 있으면 하루 이내 완료 가능)

## 리스크/유의점
- 원본 오픈소스 프로젝트가 웹 UI 스크래핑 방식이라면 ChatGPT/Gemini/Perplexity 이용약관 위반 및 로그인 세션 탈취 위험이 있으므로, 공식 API 사용을 강력 권장.
- API 키를 스크립트/설정 파일에 하드코딩하면 유출 위험 — Keychain 또는 환경 변수로 분리 필수.
- 클립보드 기반 자동화는 민감정보(비밀번호, 개인정보)가 실수로 AI 서버에 전송될 수 있어 사용 전 필터링 로직 고려.
- 종량제 API 사용 시 과도한 호출로 예상치 못한 비용 발생 가능 — 사용량 알림/한도 설정 권장.

---
원본: https://news.ycombinator.com/item?id=48047444
