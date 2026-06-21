# `gen` cheatsheet

Every column has `name`, `type` (a Snowflake type), and `gen`. Optional on any column:
`pk`, `nullable`, `autoincrement`, `default` (raw SQL), `api_field`, `null_pct` (0–1 chance of NULL).

| `gen` | Produces | Required params | Example column |
|---|---|---|---|
| `row_index` | 1-based sequential id | — | `{ "name": "ID", "type": "NUMBER", "pk": true, "gen": "row_index" }` |
| `const` | a fixed value | `value` | `{ "name": "REGION", "type": "VARCHAR", "gen": "const", "value": "APAC" }` |
| `choice` | random pick from a list | `choices` (+ optional `weights`) | `{ "name": "STATUS", "type": "VARCHAR", "gen": "choice", "choices": ["Open","Paid"], "weights": [0.4,0.6] }` |
| `enumerate` | ordered distinct values (row N → choices[N]) | `choices` (set `row_count` == len) | `{ "name": "NAME", "type": "VARCHAR", "gen": "enumerate", "choices": ["Technology","Operations","Go-to-Market"] }` |
| `int` | random integer | `min`, `max` | `{ "name": "QTY", "type": "NUMBER", "gen": "int", "min": 1, "max": 25 }` |
| `float` | random decimal | `min`, `max` (+ optional `round`) | `{ "name": "AMOUNT", "type": "FLOAT", "gen": "float", "min": 10, "max": 5000, "round": 2 }` |
| `bool` | TRUE/FALSE | optional `p_true` (default 0.5) | `{ "name": "IS_BILLABLE", "type": "BOOLEAN", "gen": "bool", "p_true": 0.8 }` |
| `date` | random date in range | `min`, `max` | `{ "name": "SPENT_DATE", "type": "DATE", "gen": "date", "min": "-12m", "max": "today" }` |
| `datetime` | random timestamp in range | `min`, `max` (+ optional `format`) | `{ "name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "gen": "datetime", "min": "-90d", "max": "today" }` |
| `sequence_date` | a regular series (row N = period N) | `step` (`day`\|`week`\|`month`), `anchor` | `{ "name": "MONTH", "type": "DATE", "gen": "sequence_date", "step": "month", "anchor": "-12m" }` |
| `template` | string from other columns in the row | `template` | `{ "name": "EMAIL", "type": "VARCHAR", "gen": "template", "template": "{FIRST_NAME\|lower}.{LAST_NAME\|lower}@acme.com" }` |
| `faker` | any Faker provider | `faker_provider` | `{ "name": "FIRST_NAME", "type": "VARCHAR", "gen": "faker", "faker_provider": "first_name" }` |
| `fk` | a foreign-key value | `ref_table` (+ optional `ref_column`, `fk_strategy`) | `{ "name": "CUSTOMER_ID", "type": "NUMBER", "gen": "fk", "ref_table": "CUSTOMERS" }` |

## Notes

- **Relative date tokens** (for `min`/`max`/`anchor`): `"today"`, `"-5y"`, `"-90d"`, `"+12m"`. Or an ISO date `"2026-01-01"`.
- **`fk_strategy`**: `"random"` (default) picks any existing parent row; `"sequential"` cycles by row index; `"parent"` is used inside a `per_parent` child table to take the current parent's id. `ref_column` defaults to the referenced table's PK.
- **`template` pipes**: `{COL}`, `{COL|lower}`, `{COL|upper}`, `{COL|slug}`. Templates can only reference columns declared **earlier** in the same table (same-row values).
- **`faker_provider`** is any zero-arg Faker method: `first_name`, `last_name`, `name`, `email`, `company`, `city`, `phone_number`, `sentence`, `paragraph`, `catch_phrase`, `bothify`, …
- **`enumerate` vs `choice`**: use `enumerate` when a small table must contain *specific distinct* values in order (dimensions); use `choice` for random categorical values across many rows.
