#!/usr/bin/env bash
# Offline Bronze load — the no-tunnel twin of BRONZE.SP_INGEST_ALL_BRONZE.
#
# Generates the SAME JSON the mock API serves and loads it into BRONZE.<entity>
# VARIANT tables, so a trial account (no External Access Integration) can run the
# FULL Bronze -> Silver -> Gold medallion. After this, flatten exactly as the
# mock-API path does:
#   snow sql -c <conn> --role ACCOUNTADMIN -f ../03_silver.sql
#   snow sql -c <conn> --role ACCOUNTADMIN -q "CALL DEMO_EMPLOYEE_APP.SILVER.SP_BUILD_SILVER();"
#
# Reuses the mock API's serializers (../../mock_api) so the Bronze JSON matches the
# live ingest. Needs Faker (pip install -r requirements.txt at the repo root).
#
#   ./seed_bronze.sh --connection <conn> [--database DB] [--seed N] [--today YYYY-MM-DD] [--dry-run]
set -euo pipefail
cd "$(dirname "$0")"

CONN=""; DB="DEMO_EMPLOYEE_APP"; SEED=42; TODAY=""; DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --connection) CONN="$2"; shift 2;;
  --database)   DB="$2"; shift 2;;
  --seed)       SEED="$2"; shift 2;;
  --today)      TODAY="$2"; shift 2;;
  --dry-run)    DRY=1; shift;;
  -h|--help) echo "usage: $0 --connection <conn> [--database DB] [--seed N] [--today YYYY-MM-DD] [--dry-run]"; exit 0;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; done
[ -n "$CONN" ] || { echo "error: --connection is required (resolved from your local connections.toml)" >&2; exit 2; }

# Faker is the only dep (same as the other seeders); install it at the repo root.
python3 -c "import faker" 2>/dev/null || { echo "error: Faker not installed — run: pip install -r requirements.txt (repo root)" >&2; exit 1; }

OUT="$(mktemp -t bronze_seed.XXXXXX.sql)"
TODAY_ARG=""; [ -n "$TODAY" ] && TODAY_ARG="--today $TODAY"
echo "generating Bronze JSON (seed=$SEED) ..."
# shellcheck disable=SC2086
python3 seed_bronze.py --database "$DB" --seed "$SEED" $TODAY_ARG --out "$OUT"

if [ "$DRY" = 1 ]; then
  echo "✓ dry-run: $OUT  ($(grep -c '^INSERT INTO BRONZE\.' "$OUT") INSERT statements). Not executed."
  exit 0
fi

echo "loading Bronze into $DB.BRONZE via connection '$CONN' ..."
snow sql -c "$CONN" --role ACCOUNTADMIN -f "$OUT" >/dev/null
rm -f "$OUT"
cat <<EOF
✓ Bronze loaded. Flatten to Silver, then build Gold + the semantic view:
  snow sql -c $CONN --role ACCOUNTADMIN -f ../03_silver.sql
  snow sql -c $CONN --role ACCOUNTADMIN -q "CALL ${DB}.SILVER.SP_BUILD_SILVER();"
  snow sql -c $CONN --role ACCOUNTADMIN -f ../04_gold.sql
  snow sql -c $CONN --role ACCOUNTADMIN -f ../05_semantic_analyst.sql
EOF
