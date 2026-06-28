#!/usr/bin/env bash
# Orchestrator: reseed both sources for DASHBOARD_SPS in FK-safe order
# (OmniHR -> Harvest). Flags pass through to each per-source seeder.
#   ./seed_all.sh --reset                 # full coherent rebuild of the live demo data
#   ./seed_all.sh --dry-run               # generate every source's SQL, execute nothing
#   ./seed_all.sh --reset --connection my_conn --rows 60
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect a --reset, real (non-dry-run) request so we confirm ONCE here.
RESET=0; DRY=0; SCHEMA="PUBLIC"
for a in "$@"; do
  case "$a" in --reset) RESET=1;; --dry-run) DRY=1;; esac
done
# pull --schema value if provided (for the confirmation message only)
prev=""; for a in "$@"; do [ "$prev" = "--schema" ] && SCHEMA="$a"; prev="$a"; done

if [ "$RESET" = 1 ] && [ "$DRY" = 0 ]; then
  echo "⚠️  Full reseed: this TRUNCATEs and reloads all 33 data tables (OmniHR + Harvest)"
  echo "    in schema ${SCHEMA}. The 5 app-managed tables (CHAT_*, DOCUMENT_CHUNKS, DOC_INGEST_LOG,"
  echo "    COMPANY_KNOWLEDGE_BASE) are NOT touched."
  printf "    Type the schema name (%s) to confirm: " "$SCHEMA"
  read -r CONFIRM
  [ "$CONFIRM" = "$SCHEMA" ] || { echo "aborted."; exit 1; }
  export SEED_CONFIRMED=1   # children skip their own prompt
fi

echo ""; echo "=== 1/2 OmniHR (HR / org / recruitment / leave) ==="
bash "$HERE/seed_omnihr.sh" "$@"
echo ""; echo "=== 2/2 Harvest (delivery / time / billing) ==="
bash "$HERE/seed_harvest.sh" "$@"

echo ""; echo "✓ All sources seeded."
