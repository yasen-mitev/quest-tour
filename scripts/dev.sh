#!/usr/bin/env bash
# Local no-Docker dev run: SQLite + local file storage, backend and frontend together.
# Writes backend/.env on first run (gitignored; env vars win over it and the deploy
# package never includes it), then runs the README's no-Docker steps:
# uv sync → alembic → sync-config → uvicorn --reload, plus the Vite dev server.
# Runs in the foreground; Ctrl-C stops both. Every output line is tagged
# [backend] / [frontend] so the interleaved logs stay readable.
#
# Options:
#   --auth dev|password|entra  admin sign-in mode (ADMIN_AUTH_PROVIDER) for this run; for
#                              password/entra, ADMIN_BOOTSTRAP_EMAIL/PASSWORD default to dev values
#   --keep-db                  keep the SQLite dev database instead of starting fresh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() { sed -n '9,12p' "$0" | sed 's/^# \{0,1\}//' >&2; }

auth_flag=""
keep_db=0
while [ $# -gt 0 ]; do
  case "$1" in
    --auth)
      [ $# -ge 2 ] || { echo "[dev] --auth needs a value" >&2; usage; exit 1; }
      auth_flag="$2"; shift 2 ;;
    --auth=*) auth_flag="${1#*=}"; shift ;;
    --keep-db) keep_db=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[dev] unknown option: $1" >&2; usage; exit 1 ;;
  esac
done
case "$auth_flag" in
  ""|dev|password|entra) ;;
  *) echo "[dev] --auth must be dev, password or entra (got: $auth_flag)" >&2; exit 1 ;;
esac
# Exported so every child (alembic, sync-config, uvicorn) sees the same settings.
# The bootstrap password is a throwaway: the dev database is local (and wiped per run by default).
if [ -n "$auth_flag" ]; then
  export ADMIN_AUTH_PROVIDER="$auth_flag"
  if [ "$auth_flag" != dev ]; then
    export ADMIN_BOOTSTRAP_EMAIL="${ADMIN_BOOTSTRAP_EMAIL:-admin@example.com}"
    export ADMIN_BOOTSTRAP_PASSWORD="${ADMIN_BOOTSTRAP_PASSWORD:-dev-password-123}"
  fi
fi

# One tagger for both phases: setup banners and piped command output share it.
# $'..' makes these real ESC sequences; printf only interprets escapes in its
# format string, so arguments must carry actual control characters.
C_BACKEND=$'\033[36m'    # cyan
C_FRONTEND=$'\033[32m'   # green
banner() { printf '%s[%s]\033[0m %s\n' "$2" "$1" "$3"; }
# Prefixes every piped line with the component it came from; fflush keeps tags in order.
label_output() {
  awk -v tag="$1" -v color="$2" '{ printf "%s[%s]\033[0m %s\n", color, tag, $0; fflush() }'
}

missing=()
command -v uv >/dev/null || missing+=("uv")
command -v npm >/dev/null || missing+=("npm")
if [ "${#missing[@]}" -gt 0 ]; then
  echo "[dev] Missing on PATH: ${missing[*]} (see README prerequisites)." >&2
  exit 1
fi

if [ ! -f "$ROOT/backend/.env" ]; then
  cat > "$ROOT/backend/.env" <<'EOF'
DATABASE_URL=sqlite:///./dev.db
HOST_ID=default
PUBLIC_BASE_URL=http://localhost:5173
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=.storage
CONFIG_DIR=config
ADMIN_DEV_EMAILS=admin@example.com
EOF
  banner backend "$C_BACKEND" "==> wrote backend/.env (SQLite, local file storage)"
fi

# Effective setting: env var wins over backend/.env (same precedence as pydantic-settings).
# `|| true`: a missing key must not trip set -e/pipefail.
env_value() {
  local key=$1
  if [ -n "${!key:-}" ]; then printf '%s' "${!key}"; return; fi
  { grep -E "^$key=" "$ROOT/backend/.env" | head -1 | cut -d= -f2- | xargs; } || true
}

# Fail before the slow setup steps rather than when uvicorn refuses to start.
auth_mode="$(env_value ADMIN_AUTH_PROVIDER)"
auth_mode="${auth_mode:-dev}"
if [ "$auth_mode" = password ] && {
  [ -z "$(env_value ADMIN_BOOTSTRAP_EMAIL)" ] || [ -z "$(env_value ADMIN_BOOTSTRAP_PASSWORD)" ]
}; then
  echo "[dev] ADMIN_AUTH_PROVIDER=password needs ADMIN_BOOTSTRAP_EMAIL and" \
    "ADMIN_BOOTSTRAP_PASSWORD (or run ./scripts/dev.sh --auth password)." >&2
  exit 1
fi
# Settings itself rejects entra mode without these, so even alembic would fail.
if [ "$auth_mode" = entra ]; then
  missing_entra=()
  for key in ADMIN_ENTRA_TENANT_ID ADMIN_ENTRA_CLIENT_ID ADMIN_ENTRA_CLIENT_SECRET \
    ADMIN_ENTRA_REDIRECT_URI ADMIN_ENTRA_GROUP_OBJECT_ID; do
    [ -n "$(env_value "$key")" ] || missing_entra+=("$key")
  done
  if [ "${#missing_entra[@]}" -gt 0 ]; then
    echo "[dev] ADMIN_AUTH_PROVIDER=entra needs: ${missing_entra[*]}" >&2
    exit 1
  fi
fi

cd "$ROOT/backend"
banner backend "$C_BACKEND" "==> uv sync"
if ! uv sync 2>&1 | label_output backend "$C_BACKEND"; then
  banner backend "$C_BACKEND" "==> uv sync failed, retrying with Python 3.13"
  uv sync --python 3.13 2>&1 | label_output backend "$C_BACKEND"
fi

# Fresh start on every run: drop the dev database so old runs (e.g. a team stuck on
# "Time's up") don't linger; alembic recreates the schema and sync-config re-issues links.
# The path comes from .env (written above; env vars win if the user customized it).
# Non-sqlite URLs pass through unchanged and then fail the -f test, i.e. a no-op.
# --keep-db skips this, e.g. to check that admins and password changes survive a restart.
db_file="$(grep -E '^DATABASE_URL=' "$ROOT/backend/.env" | head -1 | sed -E 's|^DATABASE_URL=sqlite:///\.?/?||')"
if [ "$keep_db" = 1 ]; then
  banner backend "$C_BACKEND" "==> keeping dev database (--keep-db)"
elif [ -n "$db_file" ] && [ -f "$ROOT/backend/$db_file" ]; then
  rm -f "$ROOT/backend/$db_file" "$ROOT/backend/$db_file"-journal "$ROOT/backend/$db_file"-wal "$ROOT/backend/$db_file"-shm
  banner backend "$C_BACKEND" "==> removed dev database $db_file (fresh start)"
fi

banner backend "$C_BACKEND" "==> alembic upgrade head"
uv run alembic upgrade head 2>&1 | label_output backend "$C_BACKEND"

banner backend "$C_BACKEND" "==> sync-config (prints the team game links)"
# Keep the raw output: the game links are re-printed in the final summary.
sync_output="$(uv run sync-config 2>&1)"
printf '%s\n' "$sync_output" | label_output backend "$C_BACKEND"

cd "$ROOT/frontend"
banner frontend "$C_FRONTEND" "==> npm install (skipped when node_modules exists)"
if [ ! -d node_modules ]; then
  npm install 2>&1 | label_output frontend "$C_FRONTEND"
fi

echo
printf '[dev] %s\n' \
  "==> Starting backend on :8000 and frontend on :5173." \
  "==> Ctrl-C stops both servers." \
  ""
printf '[dev] Game links:\n'
printf '%s\n' "$sync_output" | grep 'http' | sed 's/^[[:space:]]*//' | while IFS= read -r link; do
  printf '[dev]   %s\n' "$link"
done

# The sign-in hint follows the effective mode and settings (env or .env) so it stays truthful
# after manual edits; with nothing to suggest only the URL line is printed.
printf '[dev] Admin panel: http://localhost:5173/admin (%s sign-in)\n' "$auth_mode"
case "$auth_mode" in
  dev)
    admin_email="$(env_value ADMIN_DEV_EMAILS | cut -d, -f1 | xargs)"
    if [ -n "$admin_email" ]; then
      printf '[dev]   sign in as %s — the magic link appears on the login screen\n' "$admin_email"
    fi
    ;;
  password|entra)
    admin_email="$(env_value ADMIN_BOOTSTRAP_EMAIL)"
    if [ -n "$admin_email" ]; then
      printf '[dev]   sign in as %s with ADMIN_BOOTSTRAP_PASSWORD' "$admin_email"
      # Echo the password only when it is this script's throwaway default, never a user's own.
      if [ "$(env_value ADMIN_BOOTSTRAP_PASSWORD)" = dev-password-123 ]; then
        printf ' (dev-password-123)'
      fi
      printf '\n[dev]   seeded on first start only; reset with: (cd backend && uv run admin-password --email %s)\n' \
        "$admin_email"
    fi
    ;;
esac

# Job control in a script gives each background job its own process group, so a single
# negative-PID kill takes down the whole pipeline (server + label filter). With groups
# separate, Ctrl-C reaches this script only, and the trap forwards it to both groups.
set -m

start_backend() {
  cd "$ROOT/backend"
  uv run uvicorn questtour.main:create_app --factory --reload 2>&1 \
    | label_output backend "$C_BACKEND"
}
start_frontend() {
  cd "$ROOT/frontend"
  npm run dev 2>&1 | label_output frontend "$C_FRONTEND"
}

start_backend & backend_pid=$!
start_frontend & frontend_pid=$!

cleaned=0
cleanup() {
  ((cleaned)) && return 0
  cleaned=1
  echo
  echo "[dev] ==> Stopping backend and frontend..."
  kill -- "-$backend_pid" "-$frontend_pid" 2>/dev/null || true
  wait
}
trap cleanup INT TERM EXIT
wait
