#!/usr/bin/env python3
"""Build the in-memory OmniHR + Harvest dataset the mock API serves.

Reuses the seeders' generation engine (_seedlib.build_rows) and the seeders'
profiles (profiles_omnihr.json + profiles_harvest.json) — so the JSON this API
serves is the SAME synthetic data the seeders load into Snowflake. One data brain.

OmniHR and Harvest are generated together in a single call so cross-source foreign
keys are coherent (HARVEST_USERS.EMPLOYEE_ID, TIME_ENTRIES.EMPLOYEE_ID, … all point
at real EMPLOYEES rows). Everything is in-memory, so no `fetch_external` / DB reads.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDERS = HERE.parent / "src" / "seeders"
sys.path.insert(0, str(SEEDERS))          # import the shared engine

import _seedlib                            # noqa: E402
from schema import load_schema            # noqa: E402

PROFILE_FILES = {
    "omnihr": SEEDERS / "profiles_omnihr.json",
    "harvest": SEEDERS / "profiles_harvest.json",
}


def merged_profile() -> tuple[dict, dict]:
    """Merge the per-source profiles; return (profile, source_of_table)."""
    tables: dict = {}
    columns: dict = {}
    source_of: dict[str, str] = {}
    for src, path in PROFILE_FILES.items():
        p = json.loads(Path(path).read_text(encoding="utf-8"))
        for t in p.get("tables", {}):
            source_of[t] = src
        tables.update(p.get("tables", {}))
        columns.update(p.get("columns", {}))
    return {"tables": tables, "columns": columns}, source_of


def build(seed: int = 42, today: date | None = None):
    """Generate the full OmniHR+Harvest graph. Returns (order, data, cols, pk, source_of)."""
    cols, pk = load_schema()
    profile, source_of = merged_profile()
    targets = list(profile["tables"].keys())          # 33 OmniHR + Harvest tables
    random.seed(seed)
    _seedlib.Faker.seed(seed)
    order, data = _seedlib.build_rows(
        cols, pk, targets, profile, default_rows=50, today=today or date.today())
    return order, data, cols, pk, source_of


# ── self-test: counts + FK coherence (no FastAPI needed) ──────────────────────
def _selftest() -> int:
    order, data, cols, pk, source_of = build()
    print(f"generated {len(order)} tables (order respects FKs)\n")

    # collect every PK value per table -> the valid id set for FK checks
    pk_sets = {t: {r.get(pk[t]) for r in rows} for t, rows in data.items() if t in pk}

    # rebuild the FK map the way the engine does, to know which cols are FKs
    pk_index: dict[str, list] = {}
    for t, c in pk.items():
        pk_index.setdefault(c, []).append(t)

    bad = 0
    total_rows = 0
    for t in order:
        rows = data[t]
        total_rows += len(rows)
        for col in cols[t]:
            cn = col["name"]
            if cn == pk.get(t):
                continue
            parent = _seedlib.resolve_fk(t, cn, pk_index)
            if not parent:
                continue
            ptable = parent.split(".")[0]
            valid = pk_sets.get(ptable, set())
            for r in rows:
                v = r.get(cn)
                if v is not None and v not in valid:
                    bad += 1
                    if bad <= 10:
                        print(f"  ✗ {t}.{cn}={v} not in {ptable} ({source_of.get(t)})")
    print(f"total rows: {total_rows}")
    if bad:
        print(f"\n✗ {bad} dangling foreign keys")
        return 1
    print("✓ all foreign keys reference real parent rows (FK-coherent across sources)")

    # spot-check a nested-able EMPLOYEES row + a cross-source HARVEST_USERS row
    emp = data["EMPLOYEES"][0]
    print(f"\nEMPLOYEES[0]: id={emp['EMPLOYEE_ID']} {emp['FIRST_NAME']} {emp['LAST_NAME']} "
          f"<{emp['EMAIL']}> {emp['TITLE']} / {emp['DEPARTMENT']} status={emp['STATUS']} "
          f"omni={emp['OMNI_EMPLOYEE_ID']} mgr={emp['MANAGER_ID']} bu={emp['BUSINESS_UNIT_ID']}")
    hu = data["HARVEST_USERS"][0]
    print(f"HARVEST_USERS[0]: user_id={hu['USER_ID']} employee_id={hu['EMPLOYEE_ID']} "
          f"(employee_id in EMPLOYEES: {hu['EMPLOYEE_ID'] in pk_sets['EMPLOYEES']})")
    te = data["TIME_ENTRIES"][0]
    print(f"TIME_ENTRIES[0]: entry={te['ENTRY_ID']} emp={te['EMPLOYEE_ID']} "
          f"proj={te['PROJECT_ID']} task={te['TASK_ID']} hours={te['HOURS']} date={te['SPENT_DATE']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
