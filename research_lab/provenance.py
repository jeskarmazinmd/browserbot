"""Conservative temporal provenance inference.

Heuristics are deliberately conservative. UNKNOWN is preferable to silently
allowing future information into an entry hypothesis. Explicit provenance
plugins/overrides can supersede these rules later.
"""

from __future__ import annotations

from research_lab.models import FieldProvenance, TemporalClass
from research_lab.plugins import REGISTRY


_POST_ENTRY = {
    "exit_price", "exit_time", "exit_timestamp", "exit_reason",
    "pnl", "pnl_usd", "ret_pct", "return_pct",
    "mfe_pct", "mae_pct", "holding_minutes",
    "time_to_mfe_minutes", "time_to_target_minutes",
    "highest_price_time", "last_observed_price", "last_observed_at",
    "stop_replay",
}

_ENTRY = {
    "strategy_id", "symbol", "setup_id", "signal_timestamp",
    "entry", "entry_price", "target", "target_price",
    "stop", "stop_price", "notional", "paper_notional",
}

_PAST_HINTS = (
    "pre_", "lookback", "rolling_", "volume", "slope", "r2",
    "return_1m", "return_2m", "return_3m", "return_5m",
    "return_10m", "return_15m", "return_30m",
    "distance_", "rebound_", "decline_", "compression_",
    "trend_", "vwap", "ema", "sma", "volatility",
)


def infer_field(field: str) -> FieldProvenance:
    for name, rule in REGISTRY.all("provenance_rule").items():
        result = rule(field)
        if result is not None:
            if not isinstance(result, FieldProvenance):
                raise TypeError(
                    f"provenance rule {name} returned "
                    f"{type(result).__name__}"
                )
            return result

    leaf = field.rsplit(".", 1)[-1].replace("[]", "")

    if leaf in _POST_ENTRY or leaf.startswith("exit_"):
        return FieldProvenance(
            field, TemporalClass.POST_ENTRY,
            "field describes an observed outcome or post-entry state",
        )

    if leaf in _ENTRY:
        return FieldProvenance(
            field, TemporalClass.ENTRY_KNOWN,
            "field is part of the signal/entry record",
        )

    if field.startswith("research_metrics."):
        return FieldProvenance(
            field, TemporalClass.PAST_DERIVED,
            "research_metrics are captured with the signal; verify source semantics",
        )

    if any(hint in leaf.lower() for hint in _PAST_HINTS):
        return FieldProvenance(
            field, TemporalClass.PAST_DERIVED,
            "name suggests a backward-looking/entry-time derived metric",
            confidence="heuristic-low",
        )

    return FieldProvenance(
        field, TemporalClass.UNKNOWN,
        "no safe temporal classification is known",
        confidence="unknown",
    )


def safe_for_entry(field: str) -> bool:
    return infer_field(field).temporal_class in {
        TemporalClass.ENTRY_KNOWN,
        TemporalClass.PAST_DERIVED,
    }
