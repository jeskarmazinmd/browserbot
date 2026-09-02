"""Paper-only duplicate of C3N25S10NH015 for prospective parity validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


PARENT_STRATEGY_ID = "C3N25S10"
STRATEGY_ID = "C3N25S10NH015DUP"
NO_NEW_HIGH_SECONDS = 15.0


def derive_nh015_duplicate(parent: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
        return None

    symbol = str(parent.get("symbol") or "")
    timestamp = str(parent.get("timestamp") or "")
    if not symbol or not timestamp:
        return None

    row = deepcopy(dict(parent))
    row.update({
        "strategy_id": STRATEGY_ID,
        "setup_id": f"{STRATEGY_ID}|{symbol}|{timestamp}",
        "source_strategy_id": PARENT_STRATEGY_ID,
        "source_setup_id": parent.get("setup_id"),
        "exit_model": "c2",
        "no_new_high_seconds": NO_NEW_HIGH_SECONDS,
        "exit_duration_sweep_seconds": 15,
        "exit_duration_sweep_parent": PARENT_STRATEGY_ID,
        "exit_duration_sweep_version": "c3_nnh_duration_v1_20260817",
        "live_order_placement": False,
    })
    return row
