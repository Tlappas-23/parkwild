#!/usr/bin/env python
"""
Secret scanner for the pre-commit hook and CI.

`--staged` looks at what is about to be committed; `--tree` walks every file
git tracks. Either way it exits 1 and names the file (never the secret) when
it finds a Mapillary token, a private key, a GitHub / AWS / OpenAI-style token,
or a `.env` file that is not the example.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# PATTERNS — BORROWED (the published formats of each token type; Mapillary's from our own token's shape)
PATTERNS = {
    "mapillary token": re.compile(r"MLY\|\d{5,}\|[0-9a-f]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "aws access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "cloudflare token": re.compile(r"\bCF_API_TOKEN\s*=\s*\S{20,}"),
}
# ALLOWED_ENV_FILES — ARBITRARY (the one env file that is documentation, not secrets)
ALLOWED_ENV_FILES = {".env.example"}
# IGNORE_MARKER — ARBITRARY
# A line carrying this marker is deliberately fake (test fixtures, docs) and is skipped.
IGNORE_MARKER = "secret-scan:ignore"
# SKIP_SUFFIXES — ARBITRARY (binary formats where a regex hit would be noise)
SKIP_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".duckdb", ".parquet", ".glb", ".gltf", ".usdz", ".zip"}


def staged_files() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def staged_content(path: str) -> str:
    return subprocess.run(["git", "show", f":{path}"], capture_output=True, text=True, errors="replace").stdout


def scan(paths: list[str], read) -> list[str]:
    findings: list[str] = []
    for path in paths:
        name = Path(path).name
        if (name == ".env" or name.endswith(".env")) and name not in ALLOWED_ENV_FILES:
            findings.append(f"{path}: environment file must never be committed")
            continue
        if Path(path).suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = read(path)
        except Exception:
            continue
        for label, pattern in PATTERNS.items():
            for line in text.splitlines():
                if IGNORE_MARKER in line:
                    continue
                if pattern.search(line):
                    findings.append(f"{path}: looks like a {label}")
                    break
    return findings


def main(argv: list[str]) -> int:
    if "--tree" in argv:
        findings = scan(tracked_files(), lambda p: Path(p).read_text(errors="replace"))
    else:
        findings = scan(staged_files(), staged_content)
    if findings:
        print("REFUSED: possible secrets found", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
