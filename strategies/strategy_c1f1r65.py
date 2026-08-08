"""Independent prospective paper experiment: C1F1 rules with pre-trend R2 >= 0.65."""

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

STRATEGY_ID = 'C1F1R65'
DESCRIPTION = 'C1F1 rules with pre-trend R2 >= 0.65'
FAMILY = 'C1F1X'
PAPER_ONLY = True
FORWARD_START_UTC = '2026-08-10T13:30:00+00:00'

CONFIG = {
    "flash_drop_pct": 1.0,
    "rebound_confirmation_pct": 0.002,
    "stop_loss_fraction": 0.02,
    "live_order_placement": False,
    "min_pre_r2": 0.65,
    "activation_gain_pct": 0.3,
    "pullback_from_high_pct": 0.2,
}


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _timestamp(event):
    for key in ("timestamp", "signal_window_end", "detected_at"):
        value = event.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _minute_et(event):
    timestamp = _timestamp(event)
    if timestamp is None:
        return None
    local = timestamp.astimezone(ZoneInfo("America/New_York"))
    return local.hour * 60 + local.minute


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    drop = _num(event.get("flash_drop_pct"), -1.0)
    if not (CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)):
        return False
    if _num(event.get("pre_r2"), -1.0) < CONFIG["min_pre_r2"]:
        return False
    return True


def refresh_event_for_entry(event: Mapping[str, Any], current_price: float) -> dict[str, Any]:
    refreshed = dict(event)
    entry = float(current_price)
    original_target = float(refreshed["target_price"])
    original_drop = float(refreshed["flash_drop_pct"])
    remaining = ((original_target / entry) - 1.0) * 100.0
    refreshed.update({
        "strategy_id": STRATEGY_ID,
        "entry_price": entry,
        "original_flash_drop_pct": original_drop,
        "original_target_price": original_target,
        "remaining_upside_pct": remaining,
        "target_price": original_target,
        "stop_price": entry * (1.0 - CONFIG["stop_loss_fraction"]),
        "rebound_confirmation_pct": CONFIG["rebound_confirmation_pct"] * 100.0,
        "stop_loss_fraction": CONFIG["stop_loss_fraction"],
        "paper_only": True,
        "live_order_placement": False,
        "forward_start_utc": FORWARD_START_UTC,
        "exit_model": 'c1',
        "activation_gain_pct": CONFIG["activation_gain_pct"],
        "pullback_from_high_pct": CONFIG["pullback_from_high_pct"],
    })
    return refreshed


def validate_confirmed_entry(event: Mapping[str, Any], min_remaining_upside_pct: float) -> tuple[bool, str | None]:
    entry = _num(event.get("entry_price"))
    target = _num(event.get("target_price"))
    original_drop = _num(event.get("original_flash_drop_pct", event.get("flash_drop_pct")))
    remaining = _num(event.get("remaining_upside_pct"), -999.0)
    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < float(min_remaining_upside_pct):
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
