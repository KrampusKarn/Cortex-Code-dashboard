#!/usr/bin/env python3
"""Validate a schema_spec.json against the kit contract.

Two layers of checking:
  1. JSON Schema  — structural validity (templates/schema_spec.schema.json).
  2. Semantic     — cross-references and per-`gen` required params that JSON
                    Schema can't express (fk targets exist, choice has choices, etc).

Usage:
    python tools/validate_spec.py path/to/schema_spec.json

Exit code 0 = valid, 1 = invalid (errors printed to stderr).
Requires: pip install jsonschema
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "templates" / "schema_spec.schema.json"

# Which params each `gen` strategy requires.
GEN_REQUIRED = {
    "const": ["value"],
    "fk": ["ref_table"],
    "choice": ["choices"],
    "int": ["min", "max"],
    "float": ["min", "max"],
    "date": ["min", "max"],
    "datetime": ["min", "max"],
    "sequence_date": ["step"],
    "template": ["template"],
    "faker": ["faker_provider"],
    "row_index": [],
    "bool": [],
}


def _minimal_structural(spec: object) -> list[str]:
    """Fallback structural check when jsonschema is unavailable."""
    errs: list[str] = []
    if not isinstance(spec, dict):
        return ["spec root is not an object."]
    for key in ("source", "app", "tables", "knowledge_base", "dashboard"):
        if key not in spec:
            errs.append(f"[structural] missing top-level key: '{key}'.")
    app = spec.get("app", {})
    for key in ("database", "schema", "warehouse", "company_name", "llm_model", "embed_model"):
        if isinstance(app, dict) and key not in app:
            errs.append(f"[structural] app missing key: '{key}'.")
    tables = spec.get("tables")
    if not isinstance(tables, list) or not tables:
        errs.append("[structural] 'tables' must be a non-empty array.")
    else:
        for i, t in enumerate(tables):
            if not isinstance(t, dict) or "name" not in t or "columns" not in t:
                errs.append(f"[structural] tables[{i}] must have 'name' and 'columns'.")
                continue
            for c in t.get("columns", []):
                if not all(k in c for k in ("name", "type", "gen")):
                    errs.append(f"[structural] {t.get('name')}: a column is missing name/type/gen.")
                    break
    return errs


def _fail(errors: list[str]) -> None:
    print(f"✗ INVALID — {len(errors)} problem(s):", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        print("usage: python tools/validate_spec.py <schema_spec.json>", file=sys.stderr)
        sys.exit(2)

    spec_path = Path(argv[1])
    if not spec_path.exists():
        _fail([f"spec file not found: {spec_path}"])
    if not SCHEMA_PATH.exists():
        _fail([f"schema not found at {SCHEMA_PATH} (run from the repo root)"])

    try:
        spec = json.loads(spec_path.read_text())
    except json.JSONDecodeError as exc:
        _fail([f"spec is not valid JSON: {exc}"])
    schema = json.loads(SCHEMA_PATH.read_text())

    errors: list[str] = []

    # ---- Layer 1: JSON Schema (full when jsonschema is installed; else a minimal fallback) ----
    try:
        from jsonschema import Draft7Validator
        for err in sorted(Draft7Validator(schema).iter_errors(spec), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            errors.append(f"[schema] {loc}: {err.message}")
    except ImportError:
        print("  ⚠ jsonschema not installed — running minimal structural checks only "
              "(pip install jsonschema for full validation).", file=sys.stderr)
        errors.extend(_minimal_structural(spec))

    # If structural validation already failed, stop here — semantic checks assume shape.
    if errors:
        _fail(errors)

    # ---- Layer 2: Semantic ----
    tables = {t["name"]: t for t in spec["tables"]}

    for t in spec["tables"]:
        has_rc = "row_count" in t
        has_pp = "per_parent" in t
        is_chat = t.get("is_chat_table", False)
        if not is_chat and has_rc == has_pp:
            errors.append(
                f"table {t['name']}: provide exactly one of row_count / per_parent "
                f"(or set is_chat_table=true)."
            )
        if has_pp and t["per_parent"]["parent"] not in tables:
            errors.append(f"table {t['name']}: per_parent.parent '{t['per_parent']['parent']}' is not a declared table.")
        if has_pp and t["per_parent"]["max"] < t["per_parent"]["min"]:
            errors.append(f"table {t['name']}: per_parent.max < per_parent.min.")

        seen_cols: set[str] = set()
        pk_count = 0
        for c in t["columns"]:
            if c["name"] in seen_cols:
                errors.append(f"table {t['name']}: duplicate column '{c['name']}'.")
            seen_cols.add(c["name"])
            if c.get("pk"):
                pk_count += 1

            gen = c["gen"]
            for req in GEN_REQUIRED.get(gen, []):
                if req not in c:
                    errors.append(f"table {t['name']}.{c['name']}: gen='{gen}' requires '{req}'.")

            if gen == "choice" and "weights" in c and len(c["weights"]) != len(c.get("choices", [])):
                errors.append(f"table {t['name']}.{c['name']}: weights length != choices length.")

            if gen == "fk":
                ref = c.get("ref_table")
                if ref and ref not in tables:
                    errors.append(f"table {t['name']}.{c['name']}: fk ref_table '{ref}' is not a declared table.")
                if c.get("fk_strategy") == "parent" and not has_pp:
                    errors.append(f"table {t['name']}.{c['name']}: fk_strategy='parent' but table has no per_parent.")

        if pk_count == 0 and not is_chat:
            errors.append(f"table {t['name']}: no primary-key column (mark one column pk=true).")

    # knowledge_base.table must be a declared table
    kb = spec["knowledge_base"]
    if kb["table"] not in tables:
        errors.append(f"knowledge_base.table '{kb['table']}' is not a declared table.")
    else:
        kb_cols = {c["name"] for c in tables[kb["table"]]["columns"]}
        if kb["content_col"] not in kb_cols:
            errors.append(f"knowledge_base.content_col '{kb['content_col']}' not in table {kb['table']}.")
        for a in kb.get("attributes", []):
            if a not in kb_cols:
                errors.append(f"knowledge_base.attributes '{a}' not in table {kb['table']}.")

    # KB source_json should resolve relative to the spec
    src = (spec_path.parent / kb["source_json"])
    if not src.exists():
        errors.append(f"knowledge_base.source_json not found: {src}")

    if errors:
        _fail(errors)

    print(f"✓ VALID — {spec_path.name}: {len(spec['tables'])} tables, "
          f"source '{spec['source']['name']}', app db '{spec['app']['database']}'.")


if __name__ == "__main__":
    main(sys.argv)
