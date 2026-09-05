#!/usr/bin/env python
"""
Provenance coverage report: which module-level constants carry a provenance
tag, and which are bare numbers implying a rigour that isn't there.

The narrative code standard requires every constant to be tagged with one of
MEASURED, DERIVED, BORROWED, ASSUMED or ARBITRARY in the comment block directly
above it, and to say what would change it. This script is the check. `--strict`
exits 1 on any untagged constant and runs in CI.

Exempt by name: paths, URLs, table/column lists and loggers, which are
locations and labels, not choices. The exemption list is itself a choice and
sits right here where it can be argued with.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = ("MEASURED", "DERIVED", "BORROWED", "ASSUMED", "ARBITRARY")
TAG_RE = re.compile(r"\b(" + "|".join(TAGS) + r")\b")
# EXEMPT_SUFFIXES — ARBITRARY (name shapes that denote locations and labels rather than choices)
EXEMPT_SUFFIXES = ("_DIR", "_PATH", "_TOML", "_MD", "_URL", "_URLS", "_COLUMNS", "_FIELDS", "_FILTER", "_TABLES", "_RE", "_NAMES", "_KEYS", "_PARTS")
EXEMPT_NAMES = {"ROOT", "API", "GRAPH_URL", "HEADERS", "SCHEMA", "LOG", "FIXTURES", "TAGS"}


def constants_in(path: Path) -> list[tuple[str, int, str | None]]:
    """(name, line, tag) for each module-level UPPER_CASE assignment."""
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    found = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if not isinstance(t, ast.Name) or not t.id.isupper() or len(t.id) < 2:
                continue
            name = t.id
            if name.startswith("_") or name in EXEMPT_NAMES or name.endswith(EXEMPT_SUFFIXES):
                continue
            # Walk up through the contiguous block of comments and sibling
            # UPPER_CASE assignments above this one, so one tagged comment can
            # cover a group of related constants (e.g. the three category codes).
            i = node.lineno - 2
            block = []
            while i >= 0:
                line = lines[i].strip()
                if line.startswith("#"):
                    block.append(line)
                elif re.match(r"^[A-Z][A-Z0-9_]*\s*[:=]", line) or line.endswith((",", "(", "{", "[", ")", "}", "]", '"')) and block == []:
                    pass    # a sibling constant (or the tail of one); keep walking
                else:
                    break
                i -= 1
            m = TAG_RE.search("\n".join(block))
            found.append((name, node.lineno, m.group(1) if m else None))
    return found


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    files = sorted((ROOT / "src" / "parkwild").glob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
    total = tagged = 0
    missing: list[str] = []
    by_tag: dict[str, int] = {t: 0 for t in TAGS}
    for f in files:
        for name, line, tag in constants_in(f):
            total += 1
            if tag:
                tagged += 1
                by_tag[tag] += 1
            else:
                missing.append(f"{f.relative_to(ROOT)}:{line} {name}")
    print(f"provenance coverage: {tagged}/{total} constants tagged")
    print("  " + ", ".join(f"{t}: {n}" for t, n in by_tag.items()))
    if missing:
        print("untagged:")
        for m in missing:
            print("  " + m)
    return 1 if (strict and missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
