#!/usr/bin/env python3
"""Parse the live DDL (../src/00_setup.sql) into the (cols, pk) structures that
_seedlib.build_rows() expects — so the mock API needs NO Snowflake connection to
boot, yet stays in lockstep with the real schema (00_setup.sql was captured from
the live account via GET_DDL).

Returns the SAME column-dict shape introspect() produces:
    cols[TABLE] = [{name, type, len, scale, nullable, identity}, ...]
    pk[TABLE]   = "PK_COLUMN"
so the seeders and the mock API share one generation engine with one schema model.
"""
from __future__ import annotations

import re
from pathlib import Path

SETUP_SQL = Path(__file__).resolve().parent.parent / "src" / "00_setup.sql"

_TABLE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);",
    re.DOTALL | re.IGNORECASE,
)
_PK = re.compile(r"primary key\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
# COL  TYPE(opt args)  <rest>     e.g. "EMAIL VARCHAR(150)", "RATING NUMBER(2,1) NOT NULL"
_COL = re.compile(r"^(\w+)\s+([A-Za-z_]+)(?:\(([0-9,\s]+)\))?\s*(.*)$")

# lines that are constraints, not columns
_NOT_A_COLUMN = re.compile(r"^\s*(primary\s+key|foreign\s+key|unique|constraint)\b", re.IGNORECASE)


def _parse_body(body: str):
    cols, pk = [], None
    for raw in body.split("\n"):
        line = raw.strip().rstrip(",").strip()
        if not line:
            continue
        m_pk = _PK.search(line)
        if m_pk:
            pk = m_pk.group(1).upper()
            continue
        if _NOT_A_COLUMN.match(line):
            continue
        m = _COL.match(line)
        if not m:
            continue
        name, base, args, rest = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
        length = scale = None
        if args:
            parts = [p.strip() for p in args.split(",") if p.strip()]
            if base in ("VARCHAR", "CHAR", "STRING", "TEXT"):
                length = int(parts[0])
            elif len(parts) == 2:                # NUMBER(precision, scale)
                scale = int(parts[1])
        cols.append({
            "name": name.upper(),
            "type": base,
            "len": length,
            "scale": scale,
            "nullable": "NOT NULL" not in rest.upper(),
            "identity": "AUTOINCREMENT" in rest.upper(),
        })
    return cols, pk


def load_schema(path: Path = SETUP_SQL):
    """Return (cols_by_table, pk_by_table) for every CREATE TABLE in the DDL."""
    text = Path(path).read_text(encoding="utf-8")
    cols: dict[str, list] = {}
    pk: dict[str, str] = {}
    for m in _TABLE.finditer(text):
        table = m.group(1).upper()
        tcols, tpk = _parse_body(m.group(2))
        cols[table] = tcols
        if tpk:
            pk[table] = tpk
    return cols, pk


if __name__ == "__main__":
    cols, pk = load_schema()
    print(f"parsed {len(cols)} tables, {len(pk)} with a primary key")
    for t in sorted(cols):
        print(f"  {t:<32} cols={len(cols[t]):<3} pk={pk.get(t)}")
