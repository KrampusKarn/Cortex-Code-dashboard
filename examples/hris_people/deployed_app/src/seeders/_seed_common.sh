#!/usr/bin/env bash
# Shared logic for the per-source seeders. NOT run directly — sourced by
# seed_omnihr.sh / seed_harvest.sh / seed_lattice.sh, which set SOURCE/PROFILE/TABLES
# and then call `run_seed`.
#
# Reads the live table structure, generates API-realistic FK-coherent rows for ONE
# source via _seedlib.py, and (unless --dry-run) loads them with `snow sql -f`.
# `--reset` TRUNCATEs the source's tables first and requires a typed confirmation.
set -euo pipefail

# Defaults (override with flags)
CONN="sevenpeaks_partner_demo"
DB="DEMO_EMPLOYEE_APP"
SCHEMA="PUBLIC"
ROWS=50
SEED=42
RESET=0
DRY_RUN=0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --connection) CONN="$2"; shift 2;;
      --database)   DB="$2"; shift 2;;
      --schema)     SCHEMA="$2"; shift 2;;
      --rows)       ROWS="$2"; shift 2;;
      --seed)       SEED="$2"; shift 2;;
      --reset)      RESET=1; shift;;
      --dry-run)    DRY_RUN=1; shift;;
      -h|--help)
        echo "usage: $0 [--connection C] [--database DB] [--schema S] [--rows N] [--seed N] [--reset] [--dry-run]"; exit 0;;
      *) echo "unknown arg: $1" >&2; exit 2;;
    esac
  done
}

# run_seed <SOURCE_NAME> <PROFILE_FILE> <TABLES_CSV>
run_seed() {
  local source_name="$1" profile="$2" tables="$3"
  local out
  out="$(mktemp -t seed_${source_name}.XXXXXX.sql)"

  echo "── Seeding source: ${source_name} ──────────────────────────────────────"
  echo "  target     : ${DB}.${SCHEMA}   (connection: ${CONN})"
  echo "  reset      : $([ "$RESET" = 1 ] && echo 'YES — TRUNCATE then reload' || echo 'no (append)')"
  echo "  dry-run    : $([ "$DRY_RUN" = 1 ] && echo 'YES — generate only' || echo 'no')"

  # Destructive guard: typed confirmation before truncating the live account.
  # The orchestrator (seed_all.sh) confirms once and sets SEED_CONFIRMED=1 to skip
  # the per-source prompt.
  if [ "$RESET" = 1 ] && [ "$DRY_RUN" = 0 ] && [ "${SEED_CONFIRMED:-0}" != 1 ]; then
    echo ""
    echo "  ⚠️  This will TRUNCATE the ${source_name} tables in ${DB}.${SCHEMA} and reload synthetic data."
    printf "  Type the schema name (%s) to confirm: " "$SCHEMA"
    read -r CONFIRM
    if [ "$CONFIRM" != "$SCHEMA" ]; then echo "  aborted."; exit 1; fi
  fi

  local reset_flag=""
  [ "$RESET" = 1 ] && reset_flag="--reset"

  echo "  generating INSERT SQL ..."
  python3 "$HERE/_seedlib.py" \
    --connection "$CONN" --database "$DB" --schema "$SCHEMA" \
    --tables "$tables" --profile "$HERE/$profile" \
    --rows "$ROWS" --seed "$SEED" --out "$out" $reset_flag

  if [ "$DRY_RUN" = 1 ]; then
    echo "  ✓ dry-run: generated SQL at $out"
    echo "    preview (first 30 lines):"
    head -n 30 "$out" | sed 's/^/      /'
    echo "    ... ($(grep -c '^INSERT' "$out") INSERT statements total). Not executed."
    return 0
  fi

  echo "  loading into ${DB}.${SCHEMA} ..."
  snow sql -c "$CONN" --role ACCOUNTADMIN -f "$out" >/dev/null
  echo "  ✓ loaded. row counts:"
  local t
  for t in ${tables//,/ }; do
    local n
    n=$(snow sql -c "$CONN" --format json -q "SELECT COUNT(*) N FROM ${DB}.${SCHEMA}.${t};" \
        | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['N'])")
    printf "      %-32s %s\n" "$t" "$n"
  done
  rm -f "$out"
}
