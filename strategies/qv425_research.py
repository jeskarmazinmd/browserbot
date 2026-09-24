"""Prospective independent research children of QV425.

Hypotheses were chosen from 2026-09-21..24 executable bid/ask forensics.
Children consume raw candidates independently; no child consumes the parent or
another child's position/signal state.
"""
from __future__ import annotations
from datetime import datetime, timezone
from . import strategy_qv425 as parent

BIRTH = "2026-09-25T13:30:00+00:00"
SPECS: dict[str, dict] = {}
def add(sid, family, **kw): SPECS[sid] = {"family": family, **kw}

add("QV4CTL", "control")
# Entry quality: QV425's defining volatility units, executable remaining upside,
# and spread.  The 6-8 unit / >=1% upside regions were strongest in discovery.
for v in (5.0, 6.0, 7.0, 8.0): add(f"QV4VU{int(v)}", "vol_units", min_vol_units=v)
for lo,hi in ((4.25,6.0),(6.0,8.0),(8.0,10.0)):
    add(f"QV4VB{str(lo).replace('.','')}{int(hi)}", "vol_band", min_vol_units=lo, max_vol_units=hi)
add("QV4VM8", "vol_units", max_vol_units=8.0)
for v in (.50,.75,1.0,1.25,1.50): add(f"QV4UP{int(v*100):03d}", "remaining_upside", min_executable_remaining_upside_pct=v)
for v in (.25,.35,.50,.75): add(f"QV4SP{int(v*100):02d}", "spread", max_entry_spread_pct=v)
add("QV4P3", "price", min_executable_entry_price=3.0)
# Failure recognition: >120m was the dominant loss bucket; checkpoints begin earlier.
for mins in (15,30,45,60,90,120): add(f"QV4FX{mins}", "fixed_time", exit_model="k_checkpoint", mode="fixed_exit", seconds=mins*60)
for mins,ret in ((30,0.0),(60,0.0),(90,0.0),(120,0.0),(60,.25),(90,.25)):
    add(f"QV4R{mins}{int(ret*100):02d}", "checkpoint_return", exit_model="k_checkpoint", mode="conditional_return", seconds=mins*60, min_return_pct=ret)
for mins,mfe in ((30,.20),(60,.20),(90,.20),(120,.20),(60,.40),(90,.40)):
    add(f"QV4M{mins}{int(mfe*100):02d}", "checkpoint_mfe", exit_model="k_checkpoint", mode="conditional_mfe", seconds=mins*60, min_mfe_pct=mfe)
for act,trail in ((.25,.15),(.25,.25),(.50,.20),(.50,.35)):
    add(f"QV4AT{int(act*100):02d}{int(trail*100):02d}", "adaptive_trail", exit_model="adaptive_trail_target", activation_gain_pct=act, trail_from_high_pct=trail)
for pct in (2.0,3.0,4.0): add(f"QV4S{int(pct)}", "stop", stop_loss_fraction=pct/100)
# Evidence-driven combinations; intentionally few to limit discovery overfit.
add("QV4XU1S50", "combo", min_executable_remaining_upside_pct=1.0, max_entry_spread_pct=.50)
add("QV4XU1V8", "combo", min_executable_remaining_upside_pct=1.0, max_vol_units=8.0)
add("QV4XU1B68", "combo", min_executable_remaining_upside_pct=1.0, min_vol_units=6.0, max_vol_units=8.0)
add("QV4XU1S50V8", "combo", min_executable_remaining_upside_pct=1.0, max_entry_spread_pct=.50, max_vol_units=8.0)
add("QV4XU1R60", "combo", min_executable_remaining_upside_pct=1.0, exit_model="k_checkpoint", mode="conditional_return", seconds=3600, min_return_pct=0.0)
add("QV4XS50R60", "combo", max_entry_spread_pct=.50, exit_model="k_checkpoint", mode="conditional_return", seconds=3600, min_return_pct=0.0)
add("QV4XU1S3", "combo", min_executable_remaining_upside_pct=1.0, stop_loss_fraction=.03)
add("QV4XU1AT", "combo", min_executable_remaining_upside_pct=1.0, exit_model="adaptive_trail_target", activation_gain_pct=.25, trail_from_high_pct=.20)

IDS=frozenset(SPECS)

def config(sid):
    cfg=dict(parent.CONFIG); cfg["live_order_placement"]=False; return cfg

def _units(event):
    drop=float(event.get("flash_drop_pct") or -1); std=float(event.get("pre30_return_std_pct") or 0)
    return drop/std if std>0 else 0.0

def accepts(sid,event,global_max_drop_pct):
    spec=SPECS[sid]
    if not parent.accepts_flash(event,global_max_drop_pct): return False
    u=_units(event)
    if u < float(spec.get("min_vol_units",4.25)): return False
    if u > float(spec.get("max_vol_units",float("inf"))): return False
    return True

def refresh(sid,event,price):
    spec=SPECS[sid]; row=parent.refresh_event_for_entry(event,price)
    row.update(strategy_id=sid, live_order_placement=False, paper_only=True,
               forward_start_utc=BIRTH, prospective_start_utc=BIRTH,
               experimental_child=True, source_strategy_id=parent.STRATEGY_ID,
               rule_version="qv425_research_v2")
    sf=float(spec.get("stop_loss_fraction",parent.CONFIG["stop_loss_fraction"]))
    row["stop_loss_fraction"]=sf; row["stop_price"]=float(price)*(1-sf)
    for key in ("exit_model","mode","seconds","min_return_pct","min_mfe_pct","required_gain_pct",
                "activation_gain_pct","trail_from_high_pct","breakeven_after_activation",
                "max_entry_spread_pct","min_executable_entry_price","max_executable_entry_price",
                "min_executable_remaining_upside_pct"):
        if key in spec: row[key]=spec[key]
    return row

def validate(sid,event,default_minimum):
    ok,reason=parent.validate_confirmed_entry(event,default_minimum)
    if not ok: return ok,reason
    try: ts=datetime.fromisoformat(str(event.get("timestamp") or "").replace("Z","+00:00"))
    except Exception: return False,"invalid_research_timestamp"
    if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc)
    if ts.astimezone(timezone.utc) < datetime.fromisoformat(BIRTH): return False,"before_prospective_start"
    return True,None
