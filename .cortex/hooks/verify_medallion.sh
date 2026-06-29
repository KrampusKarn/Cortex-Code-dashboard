#!/usr/bin/env bash
# PostToolUse hook — verify the Bronze/Silver/Gold objects the medallion-build skill just created.
#
# Cortex Code runs this AFTER a tool call. It reads the hook payload (JSON) on stdin; if the SQL that
# just ran was a medallion step (ingest / SP_BUILD_SILVER / Gold views), it queries the DEMO account and
# feeds a ✅/⚠️ summary back to the agent via `additionalContext` so the agent can self-correct. It is
# NON-BLOCKING and self-filtering: on a non-medallion call (or any error) it stays silent (exit 0).
#
# Contract (Cortex Code command hook):
#   stdin  : {"hook_event_name":"PostToolUse","tool_name":"...","tool_input":{"sql"|"command":"..."}}
#   stdout : {"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"<msg>"}}
set -uo pipefail

CONN="${CORTEX_DEMO_CONN:-sevenpeaks_partner_demo}"   # DEMO path connection; override via env if needed
DB="DEMO_EMPLOYEE_APP"

payload="$(cat)"

# The SQL/command the tool ran (handles the SQL tool's .sql and Bash's .command), lowercased.
sql="$(printf '%s' "$payload" | python3 -c '
import json,sys
try:
    ti=(json.load(sys.stdin).get("tool_input") or {})
    print((ti.get("sql") or ti.get("command") or "").lower())
except Exception:
    print("")
')"

emit() {  # print one PostToolUse additionalContext message (JSON-escaped), then stop
    printf '%s' "$1" | python3 -c '
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":sys.stdin.read()}}))'
    exit 0
}

# Which layer just ran? Match the specific proc/object, not bare schema names (bronze.sql also
# CREATEs the SILVER/GOLD schemas, so keying on "silver" alone would misfire).
if   printf '%s' "$sql" | grep -q 'sp_build_silver';            then layer=SILVER
elif printf '%s' "$sql" | grep -q 'sp_ingest';                 then layer=BRONZE
elif printf '%s' "$sql" | grep -Eq 'employee_360|view +gold\.'; then layer=GOLD
else exit 0   # not a medallion step — stay silent
fi

# Run one read-only check; return the first scalar (or "" on any error).
q() { snow sql -c "$CONN" --role ACCOUNTADMIN --format json -q "$1" 2>/dev/null \
        | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d[0][list(d[0])[0]] if d else "")
except Exception: print("")'; }

case "$layer" in
  BRONZE)
    tables="$(q "SELECT COUNT(*) AS N FROM $DB.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='BRONZE'")"
    empties="$(q "SELECT COUNT(*) AS N FROM $DB.BRONZE.BRONZE_INGEST_LOG WHERE ROW_COUNT=0")"
    [ -z "$tables" ] || [ "$tables" = "0" ] && \
      emit "⚠️ Bronze check: no BRONZE.* tables found — ingest didn't land. Re-check build/bronze.sql + the network rule + SP_INGEST_ALL_BRONZE."
    [ -n "$empties" ] && [ "$empties" != "0" ] && \
      emit "⚠️ Bronze check: $tables tables, but $empties endpoint(s) loaded 0 rows (see BRONZE.BRONZE_INGEST_LOG). Tunnel/network-rule host or an endpoint may be off."
    emit "✅ Bronze check: $tables BRONZE.* VARIANT tables loaded, every endpoint non-zero." ;;
  SILVER)
    emp="$(q "SELECT COUNT(*) AS N FROM $DB.SILVER.EMPLOYEES")"
    { [ -z "$emp" ] || [ "$emp" = "0" ]; } && \
      emit "⚠️ Silver check: SILVER.EMPLOYEES is empty — SP_BUILD_SILVER didn't flatten. Is Bronze loaded, and do the SILVER_FIELD_MAP paths match the nested JSON?"
    emit "✅ Silver check: SILVER.EMPLOYEES has $emp rows — Bronze→Silver flatten succeeded." ;;
  GOLD)
    g="$(q "SELECT COUNT(*) AS N FROM $DB.GOLD.EMPLOYEE_360")"
    [ -z "$g" ] && \
      emit "⚠️ Gold check: GOLD.EMPLOYEE_360 didn't resolve — confirm the view and its SILVER sources exist."
    emit "✅ Gold check: GOLD.EMPLOYEE_360 resolves with $g rows — the dashboard read surface is ready." ;;
esac
