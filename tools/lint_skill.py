#!/usr/bin/env python3
"""Lint a Cortex Code SKILL.md for the kit's authoring convention.

Checks:
  - YAML frontmatter present with required keys (name, description).
  - Required sections present (# When to Use, # Workflows).
  - Recommended sections present (warn only): Prerequisites, Best Practices, Examples.
  - Any `references/<file>` mentioned in the body actually exists on disk.

Usage:
    python tools/lint_skill.py path/to/SKILL.md

Exit code 0 = ok, 1 = failed. No third-party dependencies (frontmatter parsed
with a minimal parser, since SKILL.md frontmatter is simple key/value + lists).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_FRONTMATTER = ["name", "description"]
REQUIRED_SECTIONS = ["When to Use", "Workflows"]
RECOMMENDED_SECTIONS = ["Prerequisites", "Best Practices", "Examples"]


def parse_frontmatter(text: str) -> dict | None:
    """Return the frontmatter block as {key: True} for presence checks.

    We only need to know which top-level keys exist, so we record any line of
    the form 'key:' at column 0 within the leading --- ... --- fence.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    keys: dict[str, bool] = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):", line)
        if m:
            keys[m.group(1)] = True
    return keys


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        print("usage: python tools/lint_skill.py <SKILL.md>", file=sys.stderr)
        sys.exit(2)

    path = Path(argv[1])
    if not path.exists():
        print(f"✗ not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text()
    errors: list[str] = []
    warnings: list[str] = []

    fm = parse_frontmatter(text)
    if fm is None:
        errors.append("missing YAML frontmatter (file must start with a --- ... --- block).")
    else:
        for key in REQUIRED_FRONTMATTER:
            if key not in fm:
                errors.append(f"frontmatter missing required key: '{key}'.")
        if "tools" not in fm:
            warnings.append("frontmatter has no 'tools:' list (recommended for Cortex Code skills).")

    headings = set(re.findall(r"^#{1,3}\s+(.+?)\s*$", text, flags=re.MULTILINE))
    norm = {h.lstrip("0123456789. ").strip().lower() for h in headings}

    for sec in REQUIRED_SECTIONS:
        if sec.lower() not in norm:
            errors.append(f"missing required section: '# {sec}'.")
    for sec in RECOMMENDED_SECTIONS:
        if sec.lower() not in norm:
            warnings.append(f"missing recommended section: '# {sec}'.")

    # Referenced files under references/ must exist.
    for ref in sorted(set(re.findall(r"references/[A-Za-z0-9_./-]+", text))):
        if not (path.parent / ref).exists():
            errors.append(f"referenced file does not exist: {ref}")

    for w in warnings:
        print(f"  ⚠ {w}")
    if errors:
        print(f"✗ {path.parent.name}/SKILL.md — {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    name = path.read_text().split("name:", 1)[1].splitlines()[0].strip() if "name:" in text else path.parent.name
    print(f"✓ OK — skill '{name}' ({len(headings)} sections, {len(warnings)} warning(s)).")


if __name__ == "__main__":
    main(sys.argv)
