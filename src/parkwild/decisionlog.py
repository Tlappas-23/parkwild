"""
Runtime decision log.

Every filter in the pipeline records how many rows came in, how many went out,
and under what rule, as one JSON line in reports/decision_log.jsonl. When a
population vanishes between two stages, this file says which threshold ate it.
Append-only; never rewritten by code.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .config import ROOT

REPORTS_DIR = ROOT / "reports"
LOG_PATH = REPORTS_DIR / "decision_log.jsonl"


def log_filter(stage: str, rule: str, n_in: int, n_out: int, *, path: Path = LOG_PATH, **extra) -> dict:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return entry
