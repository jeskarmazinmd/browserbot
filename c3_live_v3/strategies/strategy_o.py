"""Self-contained rules for strategy O."""

STRATEGY_ID = "O"
DESCRIPTION = "Second-leg rebound setup"
FAMILY = "LS"
PAPER_ONLY = True

CONFIG = {
    "pullback_from_first_high_pct": 0.1,
    "rebound_from_pullback_low_pct": 0.1,
    "stop_loss_fraction": 0.02,
}


def update_second_leg(record, price, now):
    """Advance O's delayed-entry state from one observed price."""
    source_entry = float(
        record.get("source_entry_price", record["entry_price"])
    )
    high = max(float(record.get("first_high", source_entry)), price)
    record["first_high"] = high

    pullback_low = record.get("pullback_low")
    if pullback_low is None:
        threshold = 1.0 - (
            float(record.get("pullback_from_first_high_pct", 0.1)) / 100.0
        )
        if high > source_entry and price <= high * threshold:
            record["pullback_low"] = price
        return None, None

    pullback_low = min(float(pullback_low), price)
    record["pullback_low"] = pullback_low
    rebound = 1.0 + (
        float(record.get("rebound_from_pullback_low_pct", 0.1)) / 100.0
    )
    if price < pullback_low * rebound:
        return None, None

    timestamp = now.isoformat()
    record["entered"] = True
    record["entry_price"] = price
    record["entry_timestamp"] = timestamp
    record["second_leg_entry_time"] = timestamp
    record["target_price"] = max(
        float(record["original_target_price"]),
        price * 1.002,
    )
    record["stop_price"] = price * (
        1.0 - float(record.get("stop_loss_fraction", 0.02))
    )
    record["highest_price"] = price
    return None, None


def metadata():
    return {
        "strategy_id": STRATEGY_ID,
        "description": DESCRIPTION,
        "family": FAMILY,
        "paper_only": PAPER_ONLY,
        "config": dict(CONFIG),
    }
