# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Assistant replies "No relevant information found" for everything | Cortex Search service still indexing, or KB table empty | `SHOW CORTEX SEARCH SERVICES IN SCHEMA <db>.<schema>;` and wait for the initial build; verify `SELECT COUNT(*) FROM <db>.<schema>.<kb_table>` > 0. |
| Assistant errors on `SEARCH_PREVIEW` / `COMPLETE` | Role lacks Cortex access | `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <app.role>;` then retry. |
| `COMPLETE` errors with an unknown-model message | `app.llm_model` not available in your region | Set `app.llm_model` to a model your account/region supports, re-render `app_config.py`, redeploy. |
| `run.sh` exits at the verification step naming an empty table | `COPY INTO` rejected rows (CSV header/column-list mismatch) | Check the table's `COPY INTO` column list vs the CSV header; fix column order in the spec, regenerate that CSV, re-run. |
| The dashboard's current month/period is blank | Time-series `max` date is a literal in the past | Use `"max": "today"` (and `"-12m"` min) on date columns; regenerate without `--today`. |
| `USE WAREHOUSE` / deploy fails: warehouse not found | A warehouse name was typed manually that differs from `app.warehouse` | There is exactly one warehouse name — `app.warehouse`. Don't introduce a second; re-render so every script uses it. |
| `snow streamlit deploy` can't find the app definition | Run from the wrong directory | Run it from the bundle's `app/` dir (the one containing `snowflake.yml`). |
| `snow` auth / connection errors | Connection not configured or key/token issue | `snow connection test -c <conn>`; check `~/.snowflake/connections.toml`. Never put credentials in the repo. |
| Chat history doesn't persist across refresh | CHAT_SESSIONS / CHAT_MESSAGES missing | Confirm both exist (they are in `01_ddl.sql`); they must be `is_chat_table: true` in the spec so their DDL is generated. |
| Streamlit app loads but a dashboard query errors | A tab queries a column that isn't in the generated table | Align the tab's SQL with the spec's column names, or add the column to the spec and regenerate. |

## Quick health checks

```sql
-- data present?
SELECT COUNT(*) FROM <db>.<schema>.<kb_table>;
-- search service ready?
SHOW CORTEX SEARCH SERVICES IN SCHEMA <db>.<schema>;
-- cortex reachable from this role?
SELECT SNOWFLAKE.CORTEX.COMPLETE('<app.llm_model>', 'Say OK.');
```
