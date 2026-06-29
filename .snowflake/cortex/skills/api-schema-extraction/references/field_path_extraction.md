# Field-path extraction — nested JSON → Silver paths

This is the meaty part of step ①: turning the API's JSON into the `json_path` lineage the medallion
flatten depends on. Most of the 33 endpoints are flat; two headline resources are nested on purpose.

## The rule

For every Silver column, `json_path` is the path *inside the row object* (the element of the response
list) to its value:

- **Flat endpoint** → `json_path = lower(COLUMN_NAME)`. Record it anyway; the map is the lineage.
- **Nested endpoint** → the dotted path to the leaf (`position.name`), or the id inside a nested
  reference object (`reporting_manager.id`, `user.id`).

Downstream, `medallion-build` emits `PAYLOAD:<json_path>::<type> AS <COLUMN_NAME>` for each column, and
only the nested overrides need to land in `SILVER.SILVER_FIELD_MAP` (flat columns map automatically by
`lower(column)`).

## Worked example — `GET /api/v1/employees` (OmniHR, nested)

Sample row:

```json
{
  "id": 1,
  "system_id": "omni_1",
  "first_name": "Dana", "last_name": "Lopez",
  "work_email": "dana.lopez@acme.com",
  "employment_status": "Active",
  "hired_date": "2022-03-01",
  "position": { "name": "Senior Software Engineer" },
  "department": { "name": "Engineering" },
  "work_location": { "name": "Singapore" },
  "reporting_manager": { "id": 7, "system_id": "omni_7" }
}
```

Extraction (the columns that need a non-trivial path are the interesting ones):

| Column | type | json_path | note |
|---|---|---|---|
| `EMPLOYEE_ID` | NUMBER(38,0) | `id` | pk |
| `OMNI_EMPLOYEE_ID` | VARCHAR(64) | `system_id` | lineage id |
| `EMAIL` | VARCHAR(150) | `work_email` | renamed |
| `STATUS` | VARCHAR(20) | `employment_status` | |
| `HIRE_DATE` | DATE | `hired_date` | |
| `TITLE` | VARCHAR(150) | `position.name` | **nested** |
| `DEPARTMENT` | VARCHAR(100) | `department.name` | **nested** |
| `LOCATION` | VARCHAR(100) | `work_location.name` | **nested** |
| `MANAGER_ID` | NUMBER(38,0) | `reporting_manager.id` | **nested**, fk → EMPLOYEES |

## Worked example — `GET /v2/time_entries` (Harvest, nested)

```json
{ "id": 1001, "spent_date": "2026-06-20", "hours": 7.5, "billable": true,
  "user": { "id": 1 }, "project": { "id": 4 }, "task": { "id": 2 } }
```

| Column | type | json_path | note |
|---|---|---|---|
| `ENTRY_ID` | NUMBER(38,0) | `id` | pk |
| `SPENT_DATE` | DATE | `spent_date` | |
| `HOURS` | NUMBER(5,2) | `hours` | |
| `IS_BILLABLE` | BOOLEAN | `billable` | renamed |
| `EMPLOYEE_ID` | NUMBER(38,0) | `user.id` | **nested**, fk → EMPLOYEES |
| `PROJECT_ID` | NUMBER(38,0) | `project.id` | **nested**, fk → PROJECTS |
| `TASK_ID` | NUMBER(38,0) | `task.id` | **nested**, fk → TASKS |

These two are the only entries that produce `SILVER_FIELD_MAP` rows in the reference build; every other
endpoint is flat. Confirm against `src/03_silver.sql` (the `SILVER_FIELD_MAP` INSERT, lines ~387–402).

## JSON → Snowflake type rules

| JSON value | type |
|---|---|
| id / pk / fk | `NUMBER(38,0)` |
| short code, status, category | `VARCHAR(20)`–`VARCHAR(100)` |
| name / free text / notes | `VARCHAR(80)`–`VARCHAR(500)` |
| email / url | `VARCHAR(150)`–`VARCHAR(200)` |
| integer count | `NUMBER(38,0)` |
| money / rate / amount | `NUMBER(12,2)` (rates `NUMBER(8,2)`) |
| decimal hours / rate-% | `NUMBER(5,2)` |
| boolean | `BOOLEAN` |
| ISO date | `DATE` |
| ISO datetime | `TIMESTAMP_NTZ` |

When in doubt, match the width in `src/03_silver.sql` for the same column — that is the known-good typing the
dashboard already renders.
