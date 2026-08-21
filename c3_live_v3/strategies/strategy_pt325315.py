"""Standalone prospective paper experiment: Independent P-style entry with $3.25-$31.50 target band."""

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

STRATEGY_ID = "PT325315"
DESCRIPTION = "Independent P-style entry with $3.25-$31.50 target band"
FAMILY = "PX"
PAPER_ONLY = True
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"
CONFIG = {
    "flash_drop_pct": 1.0,
    "rebound_confirmation_pct": 0.001,
    "stop_loss_fraction": 0.05,
    "live_order_placement": False,
}


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _timestamp(event):
    try:
        parsed = datetime.fromisoformat(
            str(event.get("timestamp") or "").replace("Z", "+00:00")
        )
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _minute_et(event):
    timestamp = _timestamp(event)
    if timestamp is None:
        return None
    local = timestamp.astimezone(ZoneInfo("America/New_York"))
    return local.hour * 60 + local.minute


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    """Independently decide whether the raw flash candidate enters this module."""
    drop = _num(event.get("flash_drop_pct"), -1.0)
    if not (CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)):
        return False
    if _num(event.get('pre_return_pct'), -1e99) < 0.75:
        return False
    if _num(event.get('pre_r2'), -1e99) < 0.5:
        return False
    target = _num(event.get('target_price'), -1e99)
    return 3.25 <= target <= 31.5


def refresh_event_for_entry(event: Mapping[str, Any], current_price: float) -> dict[str, Any]:
    """Independently construct this module's rebound-confirmed entry."""
    refreshed = dict(event)
    entry = float(current_price)
    original_target = float(refreshed["target_price"])
    original_drop_pct = float(refreshed["flash_drop_pct"])
    remaining_upside_pct = ((original_target / entry) - 1.0) * 100.0
    refreshed.update({
        "strategy_id": STRATEGY_ID,
        "entry_price": entry,
        "original_flash_drop_pct": original_drop_pct,
        "original_target_price": original_target,
        "remaining_upside_pct": remaining_upside_pct,
        "target_price": original_target,
        "stop_price": entry * (1.0 - CONFIG["stop_loss_fraction"]),
        "rebound_confirmation_pct": CONFIG["rebound_confirmation_pct"] * 100.0,
        "stop_loss_fraction": CONFIG["stop_loss_fraction"],
        "paper_only": True,
        "live_order_placement": False,
        "forward_start_utc": FORWARD_START_UTC,
    })
    return refreshed


def validate_confirmed_entry(event: Mapping[str, Any], min_remaining_upside_pct: float) -> tuple[bool, str | None]:
    """Validate only this module's own confirmed-entry state."""
    entry = _num(event.get("entry_price"))
    target = _num(event.get("target_price"))
    original_drop = _num(event.get("original_flash_drop_pct", event.get("flash_drop_pct")))
    remaining = _num(event.get("remaining_upside_pct"), -999.0)
    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    minimum = float(min_remaining_upside_pct)
    if remaining < minimum:
        return False, "insufficient_remaining_upside"
    timestamp = _timestamp(event)
    birth = datetime.fromisoformat(FORWARD_START_UTC)
    if timestamp is None or timestamp.astimezone(timezone.utc) < birth:
        return False, "before_forward_start"
    return True, None


def metadata() -> dict[str, Any]:
    return {
        "strategy_id": STRATEGY_ID,
        "description": DESCRIPTION,
        "family": FAMILY,
        "paper_only": PAPER_ONLY,
        "forward_start_utc": FORWARD_START_UTC,
        "config": dict(CONFIG),
    }
