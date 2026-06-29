#!/usr/bin/env bash
# PreToolUse hook — block SQL that would destroy the app / PUBLIC layer during an agent-driven build.
#
# Cortex Code runs this BEFORE a tool call. It allows all normal medallion DDL — and even BRONZE/SILVER/
# GOLD resets — and blocks ONLY app-destructive operations (dropping the database, the PUBLIC schema, the
# Streamlit app, or a chat/RAG object). Conservative by design so it never stalls a legitimate build.
#
# Contract (Cortex Code command hook):
#   stdin : {"hook_event_name":"PreToolUse","tool_name":"...","tool_input":{"sql"|"command":"..."}}
#   block : exit 2 with a reason on stderr   |   allow : print {"decision":"allow"} and exit 0
set -uo pipefail

sql="$(cat | python3 -c '
import json,sys
try:
    ti=(json.load(sys.stdin).get("tool_input") or {})
    print((ti.get("sql") or ti.get("command") or "").lower())
except Exception:
    print("")
')"

block() { echo "Blocked by guard_medallion: $1" >&2; exit 2; }

printf '%s' "$sql" | grep -Eq 'drop +database'                              && block "DROP DATABASE — would destroy the entire app."
printf '%s' "$sql" | grep -Eq 'drop +schema[^;]*\bpublic\b'                 && block "DROP SCHEMA PUBLIC — would destroy chat / Cortex Search / the app object."
printf '%s' "$sql" | grep -Eq 'drop +streamlit'                             && block "DROP STREAMLIT — would remove the dashboard app."
printf '%s' "$sql" | grep -Eq 'drop +(table|view) [^;]*(chat_|document_chunks|company_kb_search|company_docs)' \
                                                                            && block "Would drop a PUBLIC app/RAG object (chat / docs / search)."

# Everything else proceeds — incl. building Bronze/Silver/Gold and dropping BRONZE/SILVER/GOLD for a reset.
echo '{"decision": "allow"}'
exit 0
