"""Prospective, research-only M2 exit-family fan-out.

Every child is cloned from one confirmed M2 parent signal, ensuring
identical entry timing and entry selection. Only exit behavior differs.
No child may be generated before the declared forward start.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping


PARENT_STRATEGY_ID = "M2"
FORWARD_START_UTC = "2026-08-17T13:30:00+00:00"
FAMILY_VERSION = "m2_forward_exit_v1_20260817"

FIXED_TARGETS = {
    "M2F100": 1.00,
    "M2T125": 1.25,
    "M2T150": 1.50,
}

DYNAMIC_EXITS = {
    "M2NH15": 15.0,
    "M2NH30": 30.0,
}

FAMILY_STRATEGY_IDS = tuple(
    [*FIXED_TARGETS, *DYNAMIC_EXITS]
)


def _utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
    except (TypeError, ValueError):
        return None

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def _base_child(
    parent: Mapping[str, Any],
    strategy_id: str,
    source_setup_id: str,
) -> dict[str, Any]:
    child = deepcopy(dict(parent))
    child.update({
        "strategy_id": strategy_id,
        "setup_id": f"{strategy_id}|{source_setup_id}",
        "source_strategy_id": PARENT_STRATEGY_ID,
        "source_setup_id": source_setup_id,
        "forward_start_utc": FORWARD_START_UTC,
        "paper_only": True,
        "live_order_placement": False,
        "m2_family_variant": strategy_id,
        "m2_family_version": FAMILY_VERSION,
    })
    return child


def derive_m2_family_signals(
    parent: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return five forward-only exit variants for one M2 signal."""
    if (
        str(parent.get("strategy_id") or "").upper()
        != PARENT_STRATEGY_ID
    ):
        return []

    timestamp = _utc(parent.get("timestamp"))
    forward_start = _utc(FORWARD_START_UTC)

    if (
        timestamp is None
        or forward_start is None
        or timestamp < forward_start
    ):
        return []

    symbol = str(parent.get("symbol") or "").strip()

    try:
        entry = float(parent["entry_price"])
        stop = float(parent["stop_price"])
    except (KeyError, TypeError, ValueError):
        return []

    if not symbol or entry <= 0 or stop <= 0:
        return []

    source_setup_id = str(
        parent.get("setup_id")
        or f"{PARENT_STRATEGY_ID}|{symbol}|{timestamp.isoformat()}"
    )

    children = []

    for strategy_id, target_pct in FIXED_TARGETS.items():
        child = _base_child(
            parent,
            strategy_id,
            source_setup_id,
        )
        target = entry * (1.0 + target_pct / 100.0)
        child.update({
            "target_price": target,
            "original_target_price": target,
            "exit_model": "target_stop_eod",
            "m2_fixed_target_pct": target_pct,
        })
        children.append(child)

    # For c2 models, PaperOutcomeTracker deliberately bypasses the
    # ordinary target check. target_price remains a required positive
    # record field and metadata reference; activation controls the exit.
    parent_target = parent.get("target_price")
    try:
        parent_target = float(parent_target)
    except (TypeError, ValueError):
        parent_target = entry * 1.01

    for strategy_id, seconds in DYNAMIC_EXITS.items():
        child = _base_child(
            parent,
            strategy_id,
            source_setup_id,
        )
        child.update({
            "target_price": parent_target,
            "original_target_price": parent_target,
            "exit_model": "c2",
            "activation_gain_pct": 1.0,
            "no_new_high_seconds": seconds,
        })
        children.append(child)

    return children
