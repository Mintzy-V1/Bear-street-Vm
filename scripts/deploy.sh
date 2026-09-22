#!/usr/bin/env bash
# Auto-deploy main -> beer-streets VM (54.157.92.179).
# Runs on the GitHub-hosted runner. Requires secrets:
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY
set -euo pipefail

HOST="${DEPLOY_HOST:?DEPLOY_HOST not set}"
USER="${DEPLOY_USER:?DEPLOY_USER not set}"

SSH_KEY_FILE="$(mktemp)"
trap 'rm -f "$SSH_KEY_FILE"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$SSH_KEY_FILE"
chmod 600 "$SSH_KEY_FILE"

SSH_ARGS=(-i "$SSH_KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15)
RSYNC_SSH=(-e "ssh ${SSH_ARGS[*]}")

echo "==> Deploying to ${USER}@${HOST}"

# Push tracked code (mirror), preserving VM-only state.
rsync -avz --delete "${RSYNC_SSH[@]}" \
  --exclude '.env' --exclude '*.env' --exclude '.venv/' \
  --exclude '__pycache__/' --exclude 'logs/' --exclude 'server.log' \
  --exclude 'scripmaster_NSE_EQ.json' --exclude 'models/' \
  --exclude 'Dockerfile' --exclude '.dockerignore' --exclude '.DS_Store' \
  --exclude '*.log' --exclude '.git/' --exclude 'ticker.json' \
  --exclude 'utils/upstox_token.json' \
  ./ "${USER}@${HOST}:~/bear_street_api_server/"

echo "==> Syntax check + restart (guarded to non-trading hours)"
ssh "${SSH_ARGS[@]}" "${USER}@${HOST}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd ~/bear_street_api_server
.venv/bin/python -m py_compile \
  api_server.py auto_trader.py auto_trader_exposure_expansion.py \
  session_manager.py broker_factory.py utils/bear_street_order_pricing.py \
  utils/session_ledger.py && echo "COMPILE_OK"

# Skip restart during live trading hours (09:15-15:35 IST) to avoid killing a session.
IST_HHMM=$(TZ=Asia/Kolkata date +%H%M)
if (( 10#$IST_HHMM >= 915 && 10#$IST_HHMM <= 1535 )); then
  echo "TRADING_HOURS=1 restart skipped (new code staged for next restart)"
  exit 0
fi

MASTER=$(pgrep -f 'gunicorn -w 2 -k uvicorn.workers.UvicornWorker' | head -1 || true)
if [ -n "$MASTER" ]; then
  echo "==> Restarting gunicorn (master $MASTER)"
  kill "$MASTER"
  sleep 4
fi

if screen -ls 2>/dev/null | grep -q 'mintzy-plugin'; then
  screen -S mintzy-plugin -X stuff \
    "cd ~/bear_street_api_server && .venv/bin/gunicorn -w 2 -k uvicorn.workers.UvicornWorker api_server:app --bind 0.0.0.0:8000 --access-logfile - --error-logfile - 2>&1 | tee -a server.log
"
else
  cd ~/bear_street_api_server
  nohup .venv/bin/gunicorn -w 2 -k uvicorn.workers.UvicornWorker \
    api_server:app --bind 0.0.0.0:8000 --access-logfile - --error-logfile - \
    >> server.log 2>&1 &
fi

sleep 6
curl -sf -o /dev/null http://localhost:8000/ && echo "HEALTH_OK" || { echo "HEALTH_FAIL"; exit 1; }
REMOTE

echo "==> Deploy done"