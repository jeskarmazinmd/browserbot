"""Independent flash entry states for previously parent-derived paper filters.

Each ID is admitted to the scanner as its own strategy, with its own pending
rebound and flash-signature state. Shared price measurement is market input,
not another strategy's signal.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from . import strategy_a, strategy_b, strategy_c3n25s10, strategy_pt325315, strategy_qv425
from . import pt325315_research, qv425_research, a_research
from .c3_admission_family import FILTERS, C3AdmissionFamily
from .c3_market_gate_family import GATES, C3MarketGateFamily

TIME_FILTERS = {
    "C3N25S10NH015T1230": (750, 780),
    "C3N25S10NH015T1500": (900, 930),
    "C3N25S10NH015LATE": (840, 930),
}
IDS = frozenset({"R", "S", "C4"}) | frozenset(
    {"C3F_R3FLAT", "C3F_DEN5", "C3F_P10R1", "C3F_P10R5", "C3F_VOL3"}
) | frozenset({
    "C3MG_BRD50", "C3MG_BRD45", "C3MG_BRD40",
    "C3MG_BRD35", "C3MG_B15S", "C3MG_B15L",
}) | frozenset(TIME_FILTERS) | pt325315_research.IDS | qv425_research.IDS | a_research.IDS


def source_module(strategy_id):
    if strategy_id in pt325315_research.IDS:
        return strategy_pt325315
    if strategy_id in qv425_research.IDS:
        return strategy_qv425
    if strategy_id in a_research.IDS:
        return strategy_a
    return (strategy_a if strategy_id in {"R", "S"} else
            strategy_b if strategy_id == "C4" else strategy_c3n25s10)


def config(strategy_id):
    if strategy_id in pt325315_research.IDS:
        return pt325315_research.config(strategy_id)
    if strategy_id in qv425_research.IDS:
        return qv425_research.config(strategy_id)
    if strategy_id in a_research.IDS:
        return a_research.config(strategy_id)
    cfg = dict(source_module(strategy_id).CONFIG)
    cfg["live_order_placement"] = False
    return cfg


def accepts(strategy_id, event, global_max_drop_pct):
    if strategy_id in pt325315_research.IDS:
        return pt325315_research.accepts(strategy_id, event, global_max_drop_pct)
    if strategy_id in qv425_research.IDS:
        return qv425_research.accepts(strategy_id, event, global_max_drop_pct)
    if strategy_id in a_research.IDS:
        return a_research.accepts(strategy_id, event, global_max_drop_pct)
    return source_module(strategy_id).accepts_flash(event, global_max_drop_pct)


def refresh(strategy_id, event, price):
    if strategy_id in pt325315_research.IDS:
        return pt325315_research.refresh(strategy_id, event, price)
    if strategy_id in qv425_research.IDS:
        return qv425_research.refresh(strategy_id, event, price)
    if strategy_id in a_research.IDS:
        return a_research.refresh(strategy_id, event, price)
    row = source_module(strategy_id).refresh_event_for_entry(event, price)
    row["strategy_id"] = strategy_id
    row["live_order_placement"] = False
    if strategy_id == "C4":
        row.update(exit_model="c4", activation_gain_pct=.3,
                   slope_window_seconds=30.0, negative_slope_pct_per_minute=-.2,
                   stop_price=price * .98)
    elif strategy_id in TIME_FILTERS:
        row.update(exit_model="c2", no_new_high_seconds=15.0,
                   activation_gain_pct=.3)
    return row


def validate(strategy_id, event, minimum):
    if strategy_id in pt325315_research.IDS:
        return pt325315_research.validate(strategy_id, event, minimum)
    if strategy_id in qv425_research.IDS:
        return qv425_research.validate(strategy_id, event, minimum)
    if strategy_id in a_research.IDS:
        return a_research.validate(strategy_id, event, minimum)
    return source_module(strategy_id).validate_confirmed_entry(event, minimum)


class Filters:
    def __init__(self):
        self.admission = {sid: C3AdmissionFamily() for sid in IDS if sid in FILTERS}
        self.market = {sid: C3MarketGateFamily() for sid in IDS if sid in GATES}

    def passes(self, signal, frame, market_5m, market_1m):
        sid = signal["strategy_id"]
        minute = datetime.fromisoformat(signal["timestamp"].replace("Z", "+00:00"))
        minute = minute.astimezone(ZoneInfo("America/New_York"))
        minute_et = minute.hour * 60 + minute.minute
        if sid == "R":
            return minute_et < 660
        if sid == "S":
            return (market_5m is not None and market_1m is not None
                    and market_5m >= -.15 and market_1m >= 0)
        if sid == "C4":
            return True
        if sid in pt325315_research.IDS or sid in qv425_research.IDS or sid in a_research.IDS:
            return True
        if sid in TIME_FILTERS:
            low, high = TIME_FILTERS[sid]
            return low <= minute_et < high
        # These feature calculators previously consumed a *parent signal*.
        # Feed each one only its own confirmed entry, independently. The
        # returned child is used solely as a boolean feature decision.
        own = {**signal, "strategy_id": "C3N25S10"}
        if sid in self.admission:
            return any(row["strategy_id"] == sid for row in
                       self.admission[sid].derive_batch([own], frame))
        if sid in self.market:
            return any(row["strategy_id"] == sid for row in
                       self.market[sid].derive_batch([own], frame))
        raise KeyError(sid)
