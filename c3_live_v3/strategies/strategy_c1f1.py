"""Independent filtered C1 strategy.

C1F1 independently evaluates the same flash/rebound setup family as Strategy B
but does not consume B signals. It requires a strong pre-drop linear trend
(R2 >= 0.50) and uses C1's trailing-pullback exit.

The 0.50 threshold was frozen after the 2026-08-05 prospective analysis.
This strategy is paper-only.
"""

from typing import Any, Mapping

STRATEGY_ID = "C1F1"
DESCRIPTION = "Independent C1 with pre-trend R2 >= 0.50"
PAPER_ONLY = True

CONFIG = {
    "flash_drop_pct": 1.0,
    "rebound_confirmation_pct": 0.002,
    "stop_loss_fraction": 0.02,
    "min_pre_r2": 0.50,
    "activation_gain_pct": 0.3,
    "pullback_from_high_pct": 0.2,
    "live_order_placement": False,
}


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    """Require B-like flash magnitude plus the prospective R2 filter."""
    drop = float(event.get("flash_drop_pct", 0) or 0)
    pre_r2 = float(event.get("pre_r2", -1) or -1)
    return (
        CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)
        and pre_r2 >= CONFIG["min_pre_r2"]
    )


def refresh_event_for_entry(
    event: Mapping[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """Build the independently confirmed C1F1 entry."""
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
        "exit_model": "c1",
        "activation_gain_pct": CONFIG["activation_gain_pct"],
        "pullback_from_high_pct": CONFIG["pullback_from_high_pct"],
        "stop_loss_fraction": CONFIG["stop_loss_fraction"],
    })
    return refreshed


def validate_confirmed_entry(
    event: Mapping[str, Any],
    min_remaining_upside_pct: float,
) -> tuple[bool, str | None]:
    """Apply the same confirmed-entry validity checks as B."""
    entry = float(event.get("entry_price", 0) or 0)
    target = float(event.get("target_price", 0) or 0)
    original_drop = float(
        event.get(
            "original_flash_drop_pct",
            event.get("flash_drop_pct", 0),
        ) or 0
    )
    remaining = float(event.get("remaining_upside_pct", -999) or -999)

    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < float(min_remaining_upside_pct):
        return False, "insufficient_remaining_upside"
    return True, None
