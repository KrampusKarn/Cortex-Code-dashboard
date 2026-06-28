#!/usr/bin/env bash
# Bring the *Snowflake-ingestable* (EAI) mock-API endpoint up or down.
#
# There is ONE mock API (this local FastAPI app). "EAI-enabled" just means it is
# reachable by Snowflake: local API  ->  public tunnel  ->  the network rule
# BRONZE.OMNI_HARVEST_EGRESS points at that tunnel host. The Snowflake side
# (EAI, network rule, procs, data) is created once by ../src/02_bronze.sql and PERSISTS.
#
# Two tunnel backends:
#   • ngrok  (preferred) — uses a STABLE static domain (NGROK_DOMAIN). The host never
#       changes, so the network rule is set ONCE (run first time with --set-rule) and
#       reboots need no ALTER and no ACCOUNTADMIN.
#   • cloudflare quick tunnel (fallback) — random URL each run, so the script re-points
#       the network rule on every boot.
# Backend is auto-picked: ngrok if NGROK_DOMAIN is set, else cloudflare.
#
#   ./serve_eai.sh start [--connection NAME] [--port N] [--ngrok-domain HOST]
#                        [--cloudflare] [--ngrok] [--set-rule] [--no-update-rule]
#   ./serve_eai.sh stop
#
# SECRETS: the ngrok authtoken is NOT stored here or anywhere in the repo. Add it once:
#   ngrok config add-authtoken <token>     (writes ngrok's own config, outside this repo)
# Non-secret settings (NGROK_DOMAIN/PORT/CONN) live in ./.tunnel.env (gitignored).
set -euo pipefail
cd "$(dirname "$0")"

# Non-secret local config (gitignored): NGROK_DOMAIN, PORT, CONN
# shellcheck disable=SC1091
[ -f .tunnel.env ] && source .tunnel.env

CONN="${CONN:-sevenpeaks_partner_demo}"
PORT="${PORT:-8000}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"
BACKEND="auto"        # auto -> ngrok if NGROK_DOMAIN set, else cloudflare
SET_RULE=0            # ngrok: only ALTER the rule when asked (host is stable)
UPDATE_RULE=1         # cloudflare: ALTER every boot (random host)
CMD="${1:-start}"; shift || true
while [ $# -gt 0 ]; do case "$1" in
  --connection) CONN="$2"; shift 2;;
  --port) PORT="$2"; shift 2;;
  --ngrok-domain) NGROK_DOMAIN="$2"; shift 2;;
  --cloudflare) BACKEND="cloudflare"; shift;;
  --ngrok) BACKEND="ngrok"; shift;;
  --set-rule) SET_RULE=1; shift;;
  --no-update-rule) UPDATE_RULE=0; shift;;
  *) echo "unknown arg: $1"; exit 1;;
esac; done

[ "$BACKEND" = "auto" ] && { [ -n "$NGROK_DOMAIN" ] && BACKEND="ngrok" || BACKEND="cloudflare"; }

API_PID=.api.pid; TUN_PID=.tunnel.pid; TUN_LOG=.tunnel.log

stop_one() { [ -f "$1" ] && kill "$(cat "$1")" 2>/dev/null && echo "stopped pid $(cat "$1")"; rm -f "$1"; }

if [ "$CMD" = "stop" ]; then
  stop_one "$TUN_PID"; stop_one "$API_PID"; rm -f "$TUN_LOG"
  echo "local API + tunnel stopped. Snowflake objects + data are untouched."
  exit 0
fi

# 1) deps in an isolated local venv (gitignored) -----------------------
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -c "import fastapi, uvicorn, faker" 2>/dev/null || \
  ./.venv/bin/pip install -q fastapi uvicorn faker

# 2) boot the API (only if not already serving) ------------------------
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  nohup ./.venv/bin/python -m uvicorn app:api --host 127.0.0.1 --port "$PORT" --log-level warning >/dev/null 2>&1 &
  echo $! > "$API_PID"
fi
curl -s --retry 30 --retry-delay 1 --retry-connrefused "http://127.0.0.1:$PORT/health" >/dev/null
echo "mock API serving on http://localhost:$PORT/docs"

# 3) (re)start the tunnel ---------------------------------------------
stop_one "$TUN_PID" >/dev/null 2>&1 || true; rm -f "$TUN_LOG"

if [ "$BACKEND" = "ngrok" ]; then
  command -v ngrok >/dev/null || { echo "ngrok not found — install: brew install ngrok"; exit 1; }
  [ -n "$NGROK_DOMAIN" ] || { echo "NGROK_DOMAIN not set (put it in .tunnel.env or pass --ngrok-domain)"; exit 1; }
  ngrok config check >/dev/null 2>&1 || { echo "ngrok authtoken missing — run: ngrok config add-authtoken <token>"; exit 1; }
  nohup ngrok http "$PORT" --url "https://$NGROK_DOMAIN" --log stdout > "$TUN_LOG" 2>&1 &
  echo $! > "$TUN_PID"
  URL="https://$NGROK_DOMAIN"; HOST="$NGROK_DOMAIN"
  # confirm the public endpoint is live (skip ngrok's browser interstitial)
  curl -s --retry 20 --retry-delay 1 --retry-connrefused -H 'ngrok-skip-browser-warning: true' "$URL/health" >/dev/null \
    || { echo "ngrok tunnel did not come up; see $TUN_LOG"; exit 1; }
  echo "ngrok tunnel (stable): $URL/docs"
  if [ "$SET_RULE" = "1" ]; then
    snow sql -c "$CONN" --role ACCOUNTADMIN -q \
      "ALTER NETWORK RULE DEMO_EMPLOYEE_APP.BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST=('$HOST');" >/dev/null
    echo "network rule BRONZE.OMNI_HARVEST_EGRESS -> $HOST  (set once; stable from here on)"
  else
    echo "stable host — network rule left unchanged (first-time setup: re-run with --set-rule)"
  fi
else
  command -v cloudflared >/dev/null || { echo "cloudflared not found — install: brew install cloudflared"; exit 1; }
  nohup cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate > "$TUN_LOG" 2>&1 &
  echo $! > "$TUN_PID"
  URL=""
  for _ in $(seq 1 30); do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUN_LOG" | head -1 || true)
    [ -n "$URL" ] && break
    sleep 1
  done
  [ -z "$URL" ] && { echo "tunnel URL not found; see $TUN_LOG"; exit 1; }
  HOST="${URL#https://}"
  echo "cloudflare tunnel (ephemeral): $URL/docs"
  if [ "$UPDATE_RULE" = "1" ]; then
    snow sql -c "$CONN" --role ACCOUNTADMIN -q \
      "ALTER NETWORK RULE DEMO_EMPLOYEE_APP.BRONZE.OMNI_HARVEST_EGRESS SET VALUE_LIST=('$HOST');" >/dev/null
    echo "network rule BRONZE.OMNI_HARVEST_EGRESS -> $HOST"
  fi
fi

cat <<EOF

Ready. Ingest with:
  snow sql -c $CONN --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.BRONZE.SP_INGEST_ALL_BRONZE('$URL');"
  snow sql -c $CONN --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"

Stop everything later with:  ./serve_eai.sh stop
EOF
