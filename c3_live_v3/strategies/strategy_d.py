"""Strategy D rules.

Strategy D qualifies a slightly smaller 0.90% flash drop, requires a 0.20%
rebound confirmation, and uses a 2% protective stop. It is paper-only.

This module owns Strategy D's configuration and entry-specific calculations.
Shared scanning, pending-entry lifecycle, logging, and broker management remain
in live_strategy_runner.py.
"""

from typing import Any, Mapping

STRATEGY_ID = "D"
DESCRIPTION = "0.90% flash drop, 0.20% rebound confirmation, 2% stop"

CONFIG = {
    "flash_drop_pct": 0.9,
    "rebound_confirmation_pct": 0.002,
    "stop_loss_fraction": 0.02,
    "live_order_placement": False,
}


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    """Return whether a detected flash satisfies Strategy D's drop range."""
    drop = float(event.get("flash_drop_pct", 0) or 0)
    return CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)


def refresh_event_for_entry(
    event: Mapping[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """Build Strategy D's rebound-confirmed entry snapshot."""
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
    })
    return refreshed


def validate_confirmed_entry(
    event: Mapping[str, Any],
    min_remaining_upside_pct: float,
) -> tuple[bool, str | None]:
    """Validate a rebound-confirmed Strategy D entry."""
    entry = float(event.get("entry_price", 0) or 0)
    target = float(event.get("target_price", 0) or 0)
    original_drop = float(
        event.get("original_flash_drop_pct", event.get("flash_drop_pct", 0)) or 0
    )
    remaining = float(event.get("remaining_upside_pct", -999) or -999)

    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < float(min_remaining_upside_pct):
        return False, "insufficient_remaining_upside"
    return True, None
