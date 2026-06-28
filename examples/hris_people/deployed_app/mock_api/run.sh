#!/usr/bin/env bash
# Boot the mock OmniHR + Harvest API. Defaults: port 8000, seed 42.
#
#   ./run.sh                       # http://localhost:8000  (+ /docs)
#   PORT=9000 SEED=7 ./run.sh
#
# To let Snowflake reach it (External Access can't hit localhost), expose it over
# HTTPS in a second terminal, then allowlist that host in the network rule:
#   ngrok http 8000                # -> https://<sub>.ngrok-free.app
#   cloudflared tunnel --url http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "FastAPI/uvicorn not installed. Run:  pip install -r requirements.txt" >&2
  exit 1
fi

echo "Mock OmniHR + Harvest API  ->  http://localhost:${PORT}   (Swagger: /docs)"
exec python3 -m uvicorn app:api --host "$HOST" --port "$PORT" "$@"
