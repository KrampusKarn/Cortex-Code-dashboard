#!/usr/bin/env python3
"""Endpoint map: one route per Silver table, shaped like the real OmniHR / Harvest
APIs so the extraction story is authentic and the server is re-pointable to the
real APIs later (same paths + envelopes).

- OmniHR  -> /api/v1/...   DRF-style envelope {count,next,previous,results}
- Harvest -> /v2/...       Harvest-style envelope {<resource>:[...], pagination}

Field naming defaults to snake_case of the column (EMPLOYEE_ID -> employee_id).
A few headline resources (employees, time_entries) get a NESTED shape so the
"raw nested JSON -> flatten into Silver" step of the medallion demo is visible.
"""
from __future__ import annotations

# ── source partition (mirrors the seeders' profiles) ──────────────────────────
OMNIHR_TABLES = [
    "BUSINESS_UNITS", "DEPARTMENTS_DETAIL", "SUB_DEPARTMENTS", "TEAMS",
    "EMPLOYEES", "EMPLOYEE_FIELDS", "EMPLOYEE_PII", "EMPLOYEE_COMPENSATION_DETAILS",
    "EMPLOYEE_CERTIFICATIONS", "SALARY", "EMPLOYEES_HISTORY", "HEADCOUNT_PLAN",
    "CANDIDATE_SOURCE_CATEGORIES", "CANDIDATE_SOURCES", "JOB_POSTINGS", "CANDIDATES",
    "ONBOARDING_TASKS", "LEAVE_REQUESTS",
]
HARVEST_TABLES = [
    "CLIENTS", "PROJECTS", "TASKS", "HARVEST_USERS", "PROJECT_ASSIGNMENTS",
    "PROJECT_BUDGETS", "PROJECT_TASKS", "USER_ASSIGNMENTS", "TIME_ENTRIES",
    "EXPENSE_ENTRIES", "AVAILABILITY", "UTILIZATION", "INVOICES",
    "INVOICE_LINE_ITEMS", "ESTIMATES",
]

# ── API paths (OmniHR Omni API v1 / Harvest v2 conventions) ───────────────────
OMNIHR_PATHS = {
    "EMPLOYEES": "/api/v1/employees",
    "EMPLOYEE_FIELDS": "/api/v1/employee-fields",
    "EMPLOYEE_PII": "/api/v1/employee-pii",
    "EMPLOYEE_COMPENSATION_DETAILS": "/api/v1/employee-compensation",
    "EMPLOYEE_CERTIFICATIONS": "/api/v1/employee-certifications",
    "EMPLOYEES_HISTORY": "/api/v1/employee-history",
    "SALARY": "/api/v1/compensation/salary",
    "BUSINESS_UNITS": "/api/v1/organization/business-units",
    "DEPARTMENTS_DETAIL": "/api/v1/organization/departments",
    "SUB_DEPARTMENTS": "/api/v1/organization/sub-departments",
    "TEAMS": "/api/v1/organization/teams",
    "HEADCOUNT_PLAN": "/api/v1/organization/headcount-plan",
    "CANDIDATES": "/api/v1/ats/candidates",
    "JOB_POSTINGS": "/api/v1/ats/jobs",
    "CANDIDATE_SOURCES": "/api/v1/ats/sources",
    "CANDIDATE_SOURCE_CATEGORIES": "/api/v1/ats/source-categories",
    "ONBOARDING_TASKS": "/api/v1/onboarding/tasks",
    "LEAVE_REQUESTS": "/api/v1/time-off/requests",
}
HARVEST_PATHS = {
    "CLIENTS": "/v2/clients",
    "PROJECTS": "/v2/projects",
    "TASKS": "/v2/tasks",
    "HARVEST_USERS": "/v2/users",
    "PROJECT_ASSIGNMENTS": "/v2/project_assignments",
    "PROJECT_BUDGETS": "/v2/reports/project_budget",
    "PROJECT_TASKS": "/v2/task_assignments",
    "USER_ASSIGNMENTS": "/v2/user_assignments",
    "TIME_ENTRIES": "/v2/time_entries",
    "EXPENSE_ENTRIES": "/v2/expenses",
    "AVAILABILITY": "/v2/availability",
    "UTILIZATION": "/v2/reports/uninvoiced",
    "INVOICES": "/v2/invoices",
    "INVOICE_LINE_ITEMS": "/v2/invoice_line_items",
    "ESTIMATES": "/v2/estimates",
}
# Harvest wraps its list in a key named after the resource (last path segment).
HARVEST_RESOURCE = {t: HARVEST_PATHS[t].rsplit("/", 1)[-1] for t in HARVEST_TABLES}


# ── serializers (row dict -> JSON object) ─────────────────────────────────────
def _flat(row: dict) -> dict:
    """Default: snake_case the column names, keep values as-is."""
    return {k.lower(): v for k, v in row.items()}


def _employee(row: dict) -> dict:
    """OmniHR-shaped, NESTED — the headline for the 'nested JSON -> Silver' demo."""
    mgr = row.get("MANAGER_ID")
    return {
        "id": row.get("EMPLOYEE_ID"),
        "system_id": row.get("OMNI_EMPLOYEE_ID"),
        "first_name": row.get("FIRST_NAME"),
        "last_name": row.get("LAST_NAME"),
        "work_email": row.get("EMAIL"),
        "employment_status": row.get("STATUS"),
        "hired_date": row.get("HIRE_DATE"),
        "termination_date": row.get("TERMINATION_DATE"),
        "last_working_day": row.get("LAST_WORKING_DAY"),
        "termination_reason": row.get("TERMINATION_REASON"),
        "termination_type": row.get("TERMINATION_TYPE"),
        "position": {"name": row.get("TITLE")},
        "department": {"name": row.get("DEPARTMENT")},
        "work_location": {"name": row.get("LOCATION")},
        "reporting_manager": ({"id": mgr, "system_id": f"omni_{mgr}"} if mgr else None),
        "business_unit_id": row.get("BUSINESS_UNIT_ID"),
        "sub_department_id": row.get("SUB_DEPT_ID"),
        "team_id": row.get("TEAM_ID"),
        "lattice_id": row.get("LATTICE_ID"),
    }


def _time_entry(row: dict) -> dict:
    """Harvest-shaped, NESTED — the delivery-side headline."""
    return {
        "id": row.get("ENTRY_ID"),
        "spent_date": row.get("SPENT_DATE"),
        "hours": row.get("HOURS"),
        "billable": row.get("IS_BILLABLE"),
        "notes": row.get("NOTES"),
        "user": {"id": row.get("EMPLOYEE_ID")},
        "project": {"id": row.get("PROJECT_ID")},
        "task": {"id": row.get("TASK_ID")},
    }


SERIALIZERS = {
    "EMPLOYEES": _employee,
    "TIME_ENTRIES": _time_entry,
}


def endpoint_specs(pk_by_table: dict) -> list[dict]:
    """Build the list of endpoint descriptors the app registers."""
    specs = []
    for t in OMNIHR_TABLES:
        specs.append({
            "table": t, "source": "omnihr", "path": OMNIHR_PATHS[t],
            "resource": "results", "pk": pk_by_table.get(t),
            "serializer": SERIALIZERS.get(t, _flat),
        })
    for t in HARVEST_TABLES:
        specs.append({
            "table": t, "source": "harvest", "path": HARVEST_PATHS[t],
            "resource": HARVEST_RESOURCE[t], "pk": pk_by_table.get(t),
            "serializer": SERIALIZERS.get(t, _flat),
        })
    return specs
