"""Independent paper-only C3-family experiment: 0.25% rebound, 15s no-new-high exit."""

from typing import Any, Mapping

STRATEGY_ID = 'C3N25T15'
DESCRIPTION = '0.25% rebound, 15s no-new-high exit'
FAMILY = "C3X"
PAPER_ONLY = True
EXIT_MODEL = 'c2'

CONFIG = {'flash_drop_pct': 1.0, 'rebound_confirmation_pct': 0.0025, 'stop_loss_fraction': 0.02, 'activation_gain_pct': 0.3, 'live_order_placement': False, 'no_new_high_seconds': 15.0}


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    """Independently require the B/C3 flash-drop range."""
    drop = float(event.get("flash_drop_pct", 0) or 0)
    return CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)


def refresh_event_for_entry(
    event: Mapping[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """Create this strategy's independently rebound-confirmed entry."""
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
        "exit_model": EXIT_MODEL,
        "activation_gain_pct": CONFIG["activation_gain_pct"],
    })

    for key in (
        "no_new_high_seconds",
        "pullback_from_high_pct",
        "lower_samples",
        "min_total_decline_pct",
    ):
        if key in CONFIG:
            refreshed[key] = CONFIG[key]

    return refreshed


def validate_confirmed_entry(
    event: Mapping[str, Any],
    min_remaining_upside_pct: float,
) -> tuple[bool, str | None]:
    """Apply the same confirmed-entry validity checks as Strategy B."""
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


def metadata() -> dict[str, Any]:
    return {
        "strategy_id": STRATEGY_ID,
        "description": DESCRIPTION,
        "family": FAMILY,
        "paper_only": PAPER_ONLY,
        "config": dict(CONFIG),
    }
