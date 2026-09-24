# 새 Mac에 설치 / 복구하기

Mac이 고장 나거나 바꿀 때, 다른 Mac에서 radar를 그대로 이어서 돌리는 방법.

## 무엇이 어디에 있나

| 항목 | 보관 위치 | 새 Mac에서 |
|---|---|---|
| 코드·블루프린트 | GitHub (`main`) | `git clone`으로 복구 |
| DB (`data/radar.db`) | iCloud Drive `ai-info-radar-backup/` (사이클마다 자동 백업, 14일 보관) | 설치 스크립트가 최신 백업으로 자동 복구 |
| `.env` (토큰·비밀번호) | **직접 백업해야 함** — 비밀번호 관리자 등 | 백업해 둔 값으로 다시 작성 |
| 자동 실행(launchd) | `launchd/`의 템플릿 | 설치 스크립트가 경로를 채워 등록 |

> `.env`는 비밀값이라 GitHub·iCloud에 자동으로 올리지 않습니다. 지금 쓰는 Mac의 `.env` 내용을 비밀번호 관리자에 꼭 복사해 두세요.

## 설치 순서

1. 새 Mac에 같은 Apple ID로 로그인하고 iCloud Drive가 켜져 있는지 확인 (DB 백업이 내려받아져 있어야 함)
2. 터미널에서:
   ```bash
   cd ~/Documents
   git clone https://github.com/kwyjo85/ai-info-radar.git
   cd ai-info-radar
   bash scripts/install_mac.sh
   ```
3. 처음 실행하면 `.env`가 없어서 `.env.example`을 복사해 만들고 멈춥니다. 백업해 둔 값으로 `.env`를 채운 뒤 **같은 명령을 다시 실행**하세요.
4. 스크립트가 해 주는 것:
   - uv 설치(없으면), 파이썬 의존성 설치
   - iCloud 백업에서 가장 최근 DB 복구 (`data/radar.db`가 이미 있으면 건너뜀)
   - 30분 사이클·텔레그램 봇·잠자기 방지를 launchd에 등록 (잠자기 방지를 빼려면 `--no-caffeinate`)

## 설치 뒤 직접 확인할 것

- **claude CLI**: 없으면 `curl -fsSL https://claude.ai/install.sh | bash` 후 `claude setup-token`으로 발급한 토큰을 `.env`의 `CLAUDE_CODE_OAUTH_TOKEN`에 넣기
- **git push 권한**: `git push --dry-run`이 성공해야 대시보드 배포·블루프린트 자동 동기화가 됨 (GitHub 로그인 또는 SSH 키 설정)
- **Threads 토큰**: 만료됐으면 `uv run python -m scripts.threads_auth`
- **동작 확인**: `launchctl list | grep ai-info-radar`, 30분 뒤 `logs/launchd.cycle.log`

## 옛 Mac 정리 (둘 다 돌면 텔레그램 봇이 충돌함)

```bash
for n in cycle bot caffeinate; do launchctl bootout gui/$(id -u)/com.ai-info-radar.$n; done
```
