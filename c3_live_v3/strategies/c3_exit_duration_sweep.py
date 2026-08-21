"""Research-only C3N25S10 no-new-high duration sweep.

One already-confirmed C3N25S10 entry is cloned into paper states whose only
behavioral difference is ``no_new_high_seconds``. The existing 30-second
C3N25S10 signal remains the control and is not cloned here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


PARENT_STRATEGY_ID = "C3N25S10"
DURATIONS_SECONDS = (5, 10, 15, 20, 25, 40, 50, 60, 90, 120)
SWEEP_VERSION = "c3_nnh_duration_v1_20260817"


def strategy_id_for(seconds: int) -> str:
    return f"C3N25S10NH{int(seconds):03d}"


SWEEP_STRATEGY_IDS = tuple(strategy_id_for(value) for value in DURATIONS_SECONDS)


def derive_duration_signals(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Clone one base entry into ten duration arms without recomputing entry."""
    if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
        return []
    symbol = str(parent.get("symbol") or "")
    timestamp = str(parent.get("timestamp") or "")
    if not symbol or not timestamp:
        return []

    source_setup_id = parent.get("setup_id")
    rows: list[dict[str, Any]] = []
    for seconds in DURATIONS_SECONDS:
        strategy_id = strategy_id_for(seconds)
        row = deepcopy(dict(parent))
        row.update({
            "strategy_id": strategy_id,
            "setup_id": f"{strategy_id}|{symbol}|{timestamp}",
            "source_strategy_id": PARENT_STRATEGY_ID,
            "source_setup_id": source_setup_id,
            "exit_model": "c2",
            "no_new_high_seconds": float(seconds),
            "exit_duration_sweep_seconds": int(seconds),
            "exit_duration_sweep_parent": PARENT_STRATEGY_ID,
            "exit_duration_sweep_version": SWEEP_VERSION,
            "live_order_placement": False,
        })
        rows.append(row)
    return rows
