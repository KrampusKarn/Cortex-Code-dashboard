# Cortex Code hooks — medallion governance

Two **command hooks** that watch the DEMO-path medallion build and give it guardrails. They are wired in
[`../settings.json`](../settings.json) (project-local, auto-loaded by Cortex Code) and match the SQL-running
tool. Both are self-filtering — they stay silent on any non-medallion tool call.

| Hook | Event | Job |
|---|---|---|
| [`guard_medallion.sh`](guard_medallion.sh) | **PreToolUse** (before) | **Prevent** — block SQL that would destroy the app/PUBLIC layer (DROP DATABASE / DROP SCHEMA PUBLIC / DROP STREAMLIT / drop a chat-RAG object). Allows all normal build SQL and BRONZE/SILVER/GOLD resets. |
| [`verify_medallion.sh`](verify_medallion.sh) | **PostToolUse** (after) | **Verify** — after an ingest / `SP_BUILD_SILVER` / Gold-view step runs, query the account and feed a ✅/⚠️ summary back to the agent (Bronze tables loaded? Silver flattened? `GOLD.EMPLOYEE_360` resolves?). |

**Why this split:** "are the Bronze/Silver/Gold objects correctly implemented?" can only be checked *after* the
SQL runs → **PostToolUse**. Catching a destructive statement must happen *before* → **PreToolUse**. PostToolUse
fires after every SQL call, so you get per-layer verification automatically (Bronze, then Silver, then Gold).

## The command-hook contract (so you can edit safely)

- **stdin** (JSON): `{"hook_event_name", "tool_name", "tool_input": {"sql" | "command": "..."}}`
- **PreToolUse** returns a decision: `exit 2` + stderr reason to **block**, or `{"decision":"allow"}` + `exit 0`.
- **PostToolUse** is non-blocking: print `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"…"}}`.
- Command paths are **relative to the project root** (where `.cortex/settings.json` lives).

## Setup

1. The connection defaults to your **snow default connection** (`default_connection_name` in
   `connections.toml`). Override with `export CORTEX_DEMO_CONN=<your-conn>` to target a specific one.
2. The scripts shell out to the `snow` CLI (read-only `SELECT`s) — it must be on PATH and authenticated.
3. Either commit `.cortex/settings.json` (it auto-loads) **or** paste the equivalents into Cortex Code
   Desktop → Settings → Hooks. The Desktop per-entry form is:
   ```json
   { "event": "PostToolUse", "matcher": "snowflake_sql_execute", "hook": { "type": "command", "command": "bash .cortex/hooks/verify_medallion.sh", "timeout": 120 } }
   ```

## Tuning the matcher

`settings.json` matches `snowflake_sql_execute|run_snowflake_query|Bash` because the exact SQL tool name in
your Desktop build may vary. The scripts self-filter on SQL content, so a broad matcher is safe — but to see
the real tool name, add a one-off logger hook and run one SQL:

```json
{ "event": "PreToolUse", "matcher": ".*", "hook": { "type": "command", "command": "bash -c 'cat >> .cortex/hooks/.payloads.log'", "timeout": 10 } }
```

Read `.cortex/hooks/.payloads.log`, note the `tool_name`, then narrow the matcher to it and remove the logger.
