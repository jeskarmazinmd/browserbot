"""Prospective, independent PT325315 research family.

Every child consumes the same raw market candidate independently.  No child
consumes PT325315's signal, position, or another child's state.  Shared code is
stateless configuration only.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import strategy_pt325315 as parent

NY = ZoneInfo("America/New_York")
BIRTH = "2026-09-25T13:30:00+00:00"

# Specs intentionally change one major mechanism at a time, plus a small set
# of explicit combinations. PT325315 itself is not modified.
SPECS: dict[str, dict] = {}

def add(sid, family, **kw):
    SPECS[sid] = {"family": family, **kw}

# Exact research control.
add("PT315CTL", "control")

# Failure-time / checkpoint family.
for mins in (5, 10, 15, 20, 30, 45, 60, 90):
    add(f"PT315FX{mins}", "fixed_time", exit_model="k_checkpoint", mode="fixed_exit", seconds=mins*60)
for mins, threshold in ((10,0.0),(15,0.0),(30,0.0),(60,0.0),(15,0.25),(30,0.25)):
    add(f"PT315R{mins}{int(threshold*100):02d}", "checkpoint_return", exit_model="k_checkpoint",
        mode="conditional_return", seconds=mins*60, min_return_pct=threshold)
for mins, mfe in ((10,.20),(15,.20),(30,.20),(15,.40),(30,.40),(60,.40)):
    add(f"PT315M{mins}{int(mfe*100):02d}", "checkpoint_mfe", exit_model="k_checkpoint",
        mode="conditional_mfe", seconds=mins*60, min_mfe_pct=mfe)
for mins, gain in ((10,.25),(15,.25),(30,.25),(15,.50)):
    add(f"PT315G{mins}{int(gain*100):02d}", "checkpoint_reach", exit_model="k_checkpoint",
        mode="conditional_reach", seconds=mins*60, required_gain_pct=gain)

# Hard-stop geometry (parent is 5%).
for pct in (1.0, 1.5, 2.0, 2.5, 3.0):
    add(f"PT315S{str(pct).replace('.','')}", "stop", stop_loss_fraction=pct/100.0)

# Profit protection / dynamic exits.
for act, trail in ((.25,.15),(.25,.25),(.50,.20),(.50,.35)):
    add(f"PT315AT{int(act*100):02d}{int(trail*100):02d}", "adaptive_trail",
        exit_model="adaptive_trail_target", activation_gain_pct=act, trail_from_high_pct=trail)
for pull in (.15,.25):
    add(f"PT315C1{int(pull*100):02d}", "dynamic_pullback", exit_model="c1",
        activation_gain_pct=.30, pullback_from_high_pct=pull, breakeven_after_activation=True)
for sec in (30,60):
    add(f"PT315C2{sec}", "dynamic_no_high", exit_model="c2",
        activation_gain_pct=.30, no_new_high_seconds=float(sec), breakeven_after_activation=True)
add("PT315C3A", "dynamic_lower", exit_model="c3", activation_gain_pct=.30,
    lower_samples=3, min_total_decline_pct=.10, breakeven_after_activation=True)
add("PT315C4A", "dynamic_slope", exit_model="c4", activation_gain_pct=.30,
    slope_window_seconds=30.0, negative_slope_pct_per_minute=-.20, breakeven_after_activation=True)

# Target geometry: fraction of original entry->target distance.
for scale in (.50,.75,1.25,1.50):
    add(f"PT315T{int(scale*100)}", "target", target_distance_scale=scale)

# Entry-quality axes.
for val in (1.0,1.25,1.5):
    add(f"PT315PR{int(val*100)}", "pre_return", min_pre_return_pct=val)
for val in (.60,.70,.80):
    add(f"PT315R2{int(val*100)}", "pre_r2", min_pre_r2=val)
for val in (1.25,1.50,2.0):
    add(f"PT315FD{int(val*100)}", "flash", min_flash_drop_pct=val)
for val in (3.0,4.0):
    add(f"PT315VU{int(val*10)}", "vol_units", min_flash_vol_units=val)
for val in (.20,.30):
    add(f"PT315RB{int(val*100)}", "rebound", rebound_confirmation_pct=val/100.0)
for val in (.40,.60,.80):
    add(f"PT315UP{int(val*100)}", "remaining_upside", min_remaining_upside_pct=val)

# Price/time populations suggested by the forensic split; prospective only.
add("PT315PLOW", "price", max_entry_price=5.0)
add("PT315P20", "price", min_entry_price=20.0)
add("PT315H10", "time", start_minute_et=600, end_minute_et=660)  # 10-11 ET
add("PT315H12", "time", start_minute_et=720, end_minute_et=780)  # 12-1 ET

# High-value combinations: failure recognition + materially smaller disaster stop.
for mins, stop in ((15,2.0),(30,2.0),(30,3.0),(60,2.0)):
    add(f"PT315X{mins}S{int(stop*10)}", "combo", exit_model="k_checkpoint",
        mode="conditional_return", seconds=mins*60, min_return_pct=0.0,
        stop_loss_fraction=stop/100.0)
add("PT315XBE", "combo", exit_model="c1", activation_gain_pct=.30,
    pullback_from_high_pct=.20, breakeven_after_activation=True, stop_loss_fraction=.02)
add("PT315XMF", "combo", exit_model="k_checkpoint", mode="conditional_mfe",
    seconds=15*60, min_mfe_pct=.25, stop_loss_fraction=.02)

IDS = frozenset(SPECS)


def config(strategy_id: str) -> dict:
    spec = SPECS[strategy_id]
    cfg = dict(parent.CONFIG)
    cfg["live_order_placement"] = False
    if "rebound_confirmation_pct" in spec:
        cfg["rebound_confirmation_pct"] = spec["rebound_confirmation_pct"]
    if "min_flash_drop_pct" in spec:
        cfg["flash_drop_pct"] = spec["min_flash_drop_pct"]
    return cfg


def accepts(strategy_id: str, event, global_max_drop_pct: float) -> bool:
    spec = SPECS[strategy_id]
    drop = float(event.get("flash_drop_pct") or -1)
    if not (float(spec.get("min_flash_drop_pct", 1.0)) <= drop <= float(global_max_drop_pct)):
        return False
    if float(event.get("pre_return_pct") or -1e99) < float(spec.get("min_pre_return_pct", .75)):
        return False
    if float(event.get("pre_r2") or -1e99) < float(spec.get("min_pre_r2", .5)):
        return False
    target = float(event.get("target_price") or -1e99)
    low = float(spec.get("min_target_price", 3.25))
    high = float(spec.get("max_target_price", 31.5))
    if not (low <= target <= high):
        return False
    units_min = spec.get("min_flash_vol_units")
    if units_min is not None:
        std = float(event.get("pre30_return_std_pct") or 0.0)
        if std <= 0 or drop / std < float(units_min):
            return False
    return True


def refresh(strategy_id: str, event, price: float) -> dict:
    spec = SPECS[strategy_id]
    row = parent.refresh_event_for_entry(event, price)
    row["strategy_id"] = strategy_id
    row["live_order_placement"] = False
    row["paper_only"] = True
    row["forward_start_utc"] = BIRTH
    row["experimental_child"] = True
    row["prospective_start_utc"] = BIRTH
    row["source_strategy_id"] = parent.STRATEGY_ID
    row["rule_version"] = "pt325315_research_v1"

    stop_fraction = float(spec.get("stop_loss_fraction", parent.CONFIG["stop_loss_fraction"]))
    row["stop_loss_fraction"] = stop_fraction
    row["stop_price"] = float(price) * (1.0 - stop_fraction)

    scale = spec.get("target_distance_scale")
    if scale is not None:
        original = float(row["original_target_price"])
        row["target_price"] = float(price) + (original - float(price)) * float(scale)

    # Exit parameters are copied verbatim by PaperOutcomeTracker OPTIONAL_FIELDS.
    for key in (
        "exit_model", "mode", "seconds", "min_return_pct", "min_mfe_pct",
        "required_gain_pct", "activation_gain_pct", "trail_from_high_pct",
        "pullback_from_high_pct", "no_new_high_seconds", "lower_samples",
        "min_total_decline_pct", "slope_window_seconds",
        "negative_slope_pct_per_minute", "breakeven_after_activation",
    ):
        if key in spec:
            row[key] = spec[key]
    return row


def validate(strategy_id: str, event, default_minimum: float):
    spec = SPECS[strategy_id]
    ok, reason = parent.validate_confirmed_entry(
        event, float(spec.get("min_remaining_upside_pct", default_minimum))
    )
    if not ok:
        return ok, reason
    entry = float(event.get("entry_price") or 0.0)
    if entry < float(spec.get("min_entry_price", 0.0)):
        return False, "below_research_entry_price"
    if entry > float(spec.get("max_entry_price", float("inf"))):
        return False, "above_research_entry_price"
    ts = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
    minute = ts.astimezone(NY).hour * 60 + ts.astimezone(NY).minute
    if minute < int(spec.get("start_minute_et", 0)):
        return False, "before_research_time_window"
    if minute >= int(spec.get("end_minute_et", 24*60)):
        return False, "after_research_time_window"
    return True, None
