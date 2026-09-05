"""Prospective paper-only children selected by the NH015 time study.

The discovery sample was 2026-08-17 through 2026-09-04. Children begin on
the first unseen US session, 2026-09-08, and are derived from the existing DUP
signal so entry and exit mechanics remain identical to the control.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


PARENT_STRATEGY_ID = "C3N25S10NH015DUP"
NY = ZoneInfo("America/New_York")
DISCOVERY_PERIOD = "2026-08-17..2026-09-04"
PROSPECTIVE_START_UTC = "2026-09-08T13:30:00+00:00"
SWEEP_VERSION = "nh015_selected_time_children_v1_20260905"

CHILDREN = (
    {
        "strategy_id": "C3N25S10NH015T1230",
        "conditional_filter": "12:30<=entry_time_et<13:00",
        "label": "12:30-13:00 ET",
    },
    {
        "strategy_id": "C3N25S10NH015T1500",
        "conditional_filter": "15:00<=entry_time_et<15:30",
        "label": "15:00-15:30 ET",
    },
    {
        "strategy_id": "C3N25S10NH015LATE",
        "conditional_filter": "14:00<=entry_time_et<15:30",
        "label": ">=14:00 ET through entry cutoff",
    },
    {
        "strategy_id": "C3N25S10NH015XWEAK",
        "conditional_filter": (
            "exclude 12:00-12:30 and 14:30-15:00 ET"
        ),
        "label": "all admitted times except discovery-weak windows",
    },
)
TIME_OF_DAY_STRATEGY_IDS = tuple(row["strategy_id"] for row in CHILDREN)


def _timestamp(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            return None
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _admitted(strategy_id: str, minute_et: int) -> bool:
    if strategy_id.endswith("T1230"):
        return 12 * 60 + 30 <= minute_et < 13 * 60
    if strategy_id.endswith("T1500"):
        return 15 * 60 <= minute_et < 15 * 60 + 30
    if strategy_id.endswith("LATE"):
        return 14 * 60 <= minute_et < 15 * 60 + 30
    if strategy_id.endswith("XWEAK"):
        return not (
            12 * 60 <= minute_et < 12 * 60 + 30
            or 14 * 60 + 30 <= minute_et < 15 * 60
        )
    return False


def evaluate_time_of_day_children(
    parent: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return one observable admission decision for each selected child."""
    if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
        return []
    symbol = str(parent.get("symbol") or "")
    timestamp_text = str(parent.get("timestamp") or "")
    timestamp = _timestamp(timestamp_text)
    if not symbol or timestamp is None:
        return []
    local = timestamp.astimezone(NY)
    minute_et = local.hour * 60 + local.minute
    prospective = timestamp >= datetime.fromisoformat(PROSPECTIVE_START_UTC)

    decisions = []
    for definition in CHILDREN:
        strategy_id = definition["strategy_id"]
        time_filter_passed = _admitted(strategy_id, minute_et)
        admitted = prospective and time_filter_passed
        reason = (
            "admitted"
            if admitted
            else "before_prospective_start"
            if not prospective
            else "outside_time_filter"
        )
        row = deepcopy(dict(parent))
        row.update({
            "strategy_id": strategy_id,
            "setup_id": f"{strategy_id}|{symbol}|{timestamp_text}",
            "source_strategy_id": PARENT_STRATEGY_ID,
            "source_setup_id": parent.get("setup_id"),
            "experimental_child": True,
            "discovery_period": DISCOVERY_PERIOD,
            "prospective_start_utc": PROSPECTIVE_START_UTC,
            "conditional_filter": definition["conditional_filter"],
            "time_of_day_label": definition["label"],
            "entry_minute_et": minute_et,
            "time_of_day_sweep_version": SWEEP_VERSION,
            "live_order_placement": False,
        })
        decisions.append({
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timestamp": timestamp_text,
            "entry_minute_et": minute_et,
            "conditional_filter": definition["conditional_filter"],
            "admitted": admitted,
            "reason": reason,
            "signal": row if admitted else None,
            "source_setup_id": parent.get("setup_id"),
        })
    return decisions


def derive_time_of_day_signals(
    parent: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return admitted children; retained as a simple research API."""
    return [
        decision["signal"]
        for decision in evaluate_time_of_day_children(parent)
        if decision["admitted"]
    ]
