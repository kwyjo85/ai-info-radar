# AI Info Radar

AI 자동화 정보를 모아 채점·요약하고, 쓸 만한 것은 구현 블루프린트로 만들어 텔레그램 브리핑과 대시보드로 보여주는 개인용 파이프라인. 사용자에게 보이는 답·메시지·UI 문구는 한국어.

## 구조

- `collectors/` 수집 (rss·threads·youtube·ig_dashboard) → `storage.py`(SQLite `data/radar.db`, 스키마·마이그레이션) · `article.py`(HTML→텍스트, 원문 본문 추출)
- `pipeline/process.py` 채점(haiku)·블루프린트(sonnet) · `topic.py` 수집 주제 · `llm.py` claude CLI 호출 · `usage.py` 호출 기록·비용 추정
- `scripts/cycle.py` 30분 사이클: 수집 → 처리 → `publish_dashboard.py`(gh-pages 암호화 배포) → `git_sync.py`
- `bot/main.py` 텔레그램 봇(브리핑·주제·버튼) · `bot/health.py` 이상 알림·「상태」
- `dashboard/app.py` 로컬 Streamlit(운영 현황 탭 포함) · `dashboard/ops.py` 사이클 로그·세션 사용량 파싱
- `site/index.html` 공개 대시보드 화면 · `docs/architecture.html` 구조 문서 (둘 다 gh-pages에 올라감)

## 실행

```bash
uv run python -m scripts.cycle                       # 사이클 1회 (수동)
uv run python -m pipeline.process                    # 처리만
uv run python -m scripts.publish_dashboard --no-push --out /tmp/site   # 배포 없이 빌드
uv run streamlit run dashboard/app.py                # 로컬 대시보드 (.claude/launch.json: streamlit)
launchctl kickstart gui/$(id -u)/com.ai-info-radar.cycle       # 사이클 즉시 실행
launchctl kickstart -k gui/$(id -u)/com.ai-info-radar.bot      # 봇 재시작
```

로그: `logs/launchd.cycle.log`(사이클 전체), `logs/process.log`, `logs/collect.log`, `logs/launchd.bot.log`. LLM 호출 기록: `data/llm_usage.jsonl`.

## 운영 중인 시스템이라는 점

- launchd가 **작업 폴더의 코드를 그대로** 30분마다 실행한다. 저장하는 순간 다음 사이클에 반영된다.
- `git_sync.py`는 main에서 매 사이클 블루프린트를 커밋하고 `pull --rebase --autostash` 후 **안 올라간 커밋을 모두 push**한다. 로컬 커밋은 30분 안에 원격으로 나간다. 보류하려면 브랜치에서 작업(다른 브랜치면 동기화를 건너뛰지만, 사이클은 그 브랜치 코드로 계속 돈다).
- 공개 대시보드의 화면 파일은 origin/main 버전을 쓴다. 화면 변경은 main에 push돼야 공개된다.
- 파이프라인의 `claude -p`는 도구·MCP 끔, 짧은 시스템 프롬프트, 세션 기록 안 남김(`llm.CLI_FLAGS`), haiku는 thinking 끔. 이 설정을 되돌리면 호출당 입력이 ~3만 토큰으로 늘고 헤드리스 호출이 Bash/Write를 스스로 실행한다.

## 작업 규칙 (무엇 · 왜 · 어기면)

- **push는 사용자가 "푸시해줘"라고 할 때만.** 커밋은 작업 단위로 해도 되지만 위 자동 push를 감안해 알린다. 어기면 검토 전 코드가 원격·공개 화면에 나간다.
- **DB를 바꾸는 테스트는 복사본에서.** `cp data/radar.db <scratchpad>/x.db` 후 `storage.DB_PATH`를 바꿔 실행. LLM이 필요 없는 흐름은 `llm.complete`를 스텁으로. 어기면 실제 항목 상태·점수가 바뀌어 브리핑이 틀어진다. 실데이터를 고칠 땐 먼저 백업.
- **`bot/`·`pipeline/`·`collectors/`를 고치면 봇 재시작.** 봇은 상주 프로세스라 옛 코드를 계속 쓴다(사이클은 매번 새로 뜨므로 자동 반영).
- **스키마 변경은 `storage._migrate`에 멱등으로**, 1회성 데이터 정리는 settings 플래그로 한 번만. 어기면 매 사이클 재실행되거나 재채점 루프가 생긴다.
- **로그에 토큰·URL 쿼리 노출 금지.** httpx INFO 로그는 꺼져 있고(threads access_token), 에러는 메시지만 남긴다.
- **`.env` 값은 읽거나 출력하지 않는다.** 키 이름 확인까지만.

## 완료 기준

"다 됐다"고 말하기 전에:
1. 바뀐 경로를 실제로 실행해 확인 — 파이프라인은 사이클 로그 또는 DB 복사본 실행, 화면은 브라우저 스크린샷, 봇은 재시작 후 로그.
2. 실패·건너뛴 검증은 그대로 보고 (텔레그램에서 직접 눌러보지 못한 것 등).
3. 사용자 쪽 설정이 필요한 것(.env 값, 앱 권한)은 명확히 안내.

## 멈추고 물어볼 상황

- 파일·블루프린트·DB 행 삭제, 대량 상태 변경(재채점 큐잉 포함)
- force push, 히스토리 수정, gh-pages 수동 조작
- launchd plist 교체·설치, 새 외부 서비스·유료 API 연결
- 비용이 드는 대량 LLM 호출(수십 회 이상) — 예상 비용을 먼저 제시

## 알려진 함정

- Streamlit은 `app.py`만 다시 읽고 import한 모듈(`dashboard/ops.py` 등)은 캐시한다 → 모듈을 고치면 서버 재시작.
- `st.caption`/`st.markdown`은 `$…$`를 수식으로 렌더링 → 금액은 `\$`로 이스케이프.
- 블루프린트 파일명이 한글 자모로 잘려 DB 경로와 어긋난 적이 있다(2026-09-23 생성분). 경로 비교는 NFC 정규화로.
- HN·Google 뉴스 항목의 `content`는 링크·메타데이터뿐이다. 블루프린트는 `process.ensure_body`로 원문을 가져오고, 못 가져오면 뉴스로 강등.
- 맥이 잠들면 사이클·봇이 멈춘다. 봇의 지연 알림은 깨어난 뒤 45분간 보류.
