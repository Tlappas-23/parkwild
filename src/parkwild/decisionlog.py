"""
Runtime decision log.

Every filter in the pipeline records how many rows came in, how many went out,
and under what rule, as one JSON line in reports/decision_log.jsonl. When a
population vanishes between two stages, this file says which threshold ate it.
Append-only; never rewritten by code.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .config import ROOT

REPORTS_DIR = ROOT / "reports"
LOG_PATH = REPORTS_DIR / "decision_log.jsonl"


def default_log_path() -> Path:
    """The real log, unless PARKWILD_DECISION_LOG points elsewhere. Tests and the
    smoke test set it to a temp file: the first version wrote their six-row
    fixture filters into the real ledger (E-020)."""
    override = os.environ.get("PARKWILD_DECISION_LOG")
    return Path(override) if override else LOG_PATH

# Entries written by this process, so a script can end with a summary of
# every rule that dropped rows during the run (the build spec's "when 8,000
# rows vanish, the output names the rule").
_THIS_RUN: list[dict] = []


def log_filter(stage: str, rule: str, n_in: int, n_out: int, *, path: Path | None = None, **extra) -> dict:
    """Append one line and return it. `extra` holds the parameters that made the
    decision (thresholds, keys), so the line is reproducible on its own."""
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "stage": stage,
        "rule": rule,
        "n_in": int(n_in),
        "n_out": int(n_out),
        "n_dropped": int(n_in) - int(n_out),
        **extra,
    }
    path = path or default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    _THIS_RUN.append(entry)
    return entry


def print_decision_summary() -> None:
    """Called at the end of every script: one line per filter that ran."""
    if not _THIS_RUN:
        print("decision summary: no filters ran")
        return
    print("decision summary:")
    for e in _THIS_RUN:
        print(f"  {e['stage']:<28} {e['n_in']:>9,} -> {e['n_out']:>9,}  ({e['n_dropped']:,} dropped)  {e['rule']}")


SAMPLES_DIR = REPORTS_DIR / "samples"


def record_sample(name: str, ids: list, **params) -> Path:
    """Pin a sample to disk: the seed and parameters that produced it and the
    exact ids chosen. A number that cannot be regenerated from this file is
    not a result. Overwrites: the file describes the current sample."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = SAMPLES_DIR / f"{name}.json"
    record = {"recorded": datetime.now(UTC).isoformat(timespec="seconds"), "n": len(ids), **params, "ids": ids}
    path.write_text(json.dumps(record, indent=1, default=str))
    return path
