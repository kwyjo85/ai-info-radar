#!/usr/bin/env bash
# 새 Mac에 radar 설치/복구. 여러 번 실행해도 안전(이미 된 단계는 건너뜀).
#
#   git clone https://github.com/kwyjo85/ai-info-radar.git && cd ai-info-radar
#   bash scripts/install_mac.sh              # 설치 (잠자기 방지 포함)
#   bash scripts/install_mac.sh --no-caffeinate
#
# 하는 일: 도구 확인 → 의존성 설치 → .env 준비 → iCloud 백업에서 DB 복구 → launchd 등록
# 자세한 안내: docs/SETUP.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
AGENTS="$HOME/Library/LaunchAgents"
BACKUP_DIR="${RADAR_BACKUP_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/ai-info-radar-backup}"
CAFFEINATE=1
[[ "${1:-}" == "--no-caffeinate" ]] && CAFFEINATE=0

step() { printf '\n▶ %s\n' "$1"; }
warn() { printf '  ⚠️  %s\n' "$1"; }

step "1/5 필수 도구 확인"
command -v git >/dev/null || { echo "  git이 없습니다. 'xcode-select --install' 후 다시 실행하세요."; exit 1; }
if ! command -v uv >/dev/null; then
  echo "  uv 설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
UV="$(command -v uv)"
echo "  uv: $UV"
CLAUDE="$(command -v claude || true)"
[[ -z "$CLAUDE" && -x "$HOME/.local/bin/claude" ]] && CLAUDE="$HOME/.local/bin/claude"
if [[ -n "$CLAUDE" ]]; then
  echo "  claude: $CLAUDE"
else
  warn "claude CLI 없음 — 채점에 필요합니다: curl -fsSL https://claude.ai/install.sh | bash"
fi

step "2/5 파이썬 의존성 설치"
"$UV" sync --quiet
echo "  완료"

step "3/5 .env 확인"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "  .env.example을 복사해 .env를 만들었습니다."
  echo "  비밀번호 관리자에 백업해 둔 값으로 .env를 채운 뒤 이 스크립트를 다시 실행하세요."
  exit 0
fi
for key in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
  grep -Eq "^${key}=.+" .env || warn ".env의 ${key}가 비어 있습니다 (텔레그램 봇이 동작하지 않음)"
done
if ! grep -Eq "^CLAUDE_CODE_OAUTH_TOKEN=[^ #]+" .env && ! grep -Eq "^LLM_BACKEND=api" .env; then
  warn "CLAUDE_CODE_OAUTH_TOKEN이 비어 있습니다 — 'claude setup-token'으로 발급해 넣으세요 (launchd에서 채점하려면 필요)"
fi

step "4/5 DB 복구"
mkdir -p data logs
if [[ -f data/radar.db ]]; then
  echo "  data/radar.db 이미 있음 — 건너뜀"
else
  latest="$(ls -1 "$BACKUP_DIR"/radar-*.db 2>/dev/null | sort | tail -n 1 || true)"
  if [[ -n "$latest" ]]; then
    cp "$latest" data/radar.db
    echo "  복구: $latest"
  else
    echo "  백업 없음 ($BACKUP_DIR) — 빈 DB로 새로 시작합니다"
  fi
fi

step "5/5 자동 실행(launchd) 등록"
mkdir -p "$AGENTS"
PATH_VALUE="$(dirname "$UV")"
[[ -n "$CLAUDE" && "$(dirname "$CLAUDE")" != "$PATH_VALUE" ]] && PATH_VALUE="$(dirname "$CLAUDE"):$PATH_VALUE"
PATH_VALUE="$PATH_VALUE:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

names=(cycle bot)
[[ $CAFFEINATE == 1 ]] && names+=(caffeinate)
for name in "${names[@]}"; do
  label="com.ai-info-radar.$name"
  dest="$AGENTS/$label.plist"
  sed -e "s#__ROOT__#$ROOT#g" -e "s#__UV__#$UV#g" -e "s#__PATH__#$PATH_VALUE#g" \
    "launchd/$label.plist" > "$dest"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  echo "  등록: $label"
done

cat <<EOF

✅ 설치 완료: $ROOT
  - 30분마다 수집·채점·백업·대시보드 배포·git 동기화, 텔레그램 봇 상시 실행
  - 로그: logs/launchd.cycle.log, logs/launchd.bot.log
  - 확인: launchctl list | grep ai-info-radar
  - git push가 되는지 확인하세요(대시보드 배포·블루프린트 동기화에 필요): git push --dry-run
EOF
