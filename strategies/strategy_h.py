"""Strategy H rules.

Strategy H is a broad filtered rebound setup. It accepts flash drops from
0.60% through 2.50%, requires pre-trend R² of at least 0.40, rejects pre-trend
slopes above 12% per hour, confirms after a 0.10% rebound, requires at least
0.10% remaining upside, and uses a 4% protective stop. It is paper-only.

This module owns Strategy H's configuration and entry-specific calculations.
Shared scanning, pending-entry lifecycle, logging, and broker management remain
in live_strategy_runner.py.
"""

import math
from typing import Any, Mapping

STRATEGY_ID = "H"
DESCRIPTION = "Filtered 0.60%-2.50% flash rebound with R²/slope filters and 4% stop"

CONFIG = {
    "flash_drop_pct": 0.60,
    "max_flash_drop_pct": 2.50,
    "min_pre_r2": 0.40,
    "max_pre_slope_pct_per_hour": 12.0,
    "rebound_confirmation_pct": 0.001,
    "stop_loss_fraction": 0.04,
    "min_remaining_upside_pct": 0.10,
    "live_order_placement": False,
}


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    """Return whether a detected flash satisfies all Strategy H filters."""
    drop = float(event.get("flash_drop_pct", 0) or 0)
    upper = min(float(CONFIG["max_flash_drop_pct"]), float(max_flash_drop_pct))
    if not (float(CONFIG["flash_drop_pct"]) <= drop <= upper):
        return False

    r2 = float(event.get("pre_r2", float("nan")) or float("nan"))
    if math.isnan(r2) or r2 < float(CONFIG["min_pre_r2"]):
        return False

    slope = float(
        event.get("pre_slope_pct_per_hour", float("nan")) or float("nan")
    )
    if math.isnan(slope) or slope > float(CONFIG["max_pre_slope_pct_per_hour"]):
        return False

    return True


def refresh_event_for_entry(
    event: Mapping[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """Build Strategy H's rebound-confirmed entry snapshot."""
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
    min_remaining_upside_pct: float | None = None,
) -> tuple[bool, str | None]:
    """Validate a rebound-confirmed Strategy H entry."""
    entry = float(event.get("entry_price", 0) or 0)
    target = float(event.get("target_price", 0) or 0)
    original_drop = float(
        event.get("original_flash_drop_pct", event.get("flash_drop_pct", 0)) or 0
    )
    remaining = float(event.get("remaining_upside_pct", -999) or -999)
    minimum = float(
        CONFIG["min_remaining_upside_pct"]
        if min_remaining_upside_pct is None
        else min_remaining_upside_pct
    )

    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < minimum:
        return False, "insufficient_remaining_upside"
    return True, None
