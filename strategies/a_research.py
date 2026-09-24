"""Prospective independent research children of broad Strategy A.

Hypotheses were chosen from 2026-09-21..24 executable bid/ask forensics.
The discovery sample showed strong spread/price/remaining-upside effects and a
large >120 minute loss tail; these children test those findings prospectively.
"""
from __future__ import annotations
from datetime import datetime, timezone
from . import strategy_a as parent

BIRTH="2026-09-25T13:30:00+00:00"
SPECS: dict[str,dict]={}
def add(sid,family,**kw): SPECS[sid]={"family":family,**kw}

add("ARCTL","control")
# Executable entry-quality hypotheses. Spread <=0.5%, price >=$3 and >=1.5%
# remaining upside were the strongest discovery dimensions.
for v in (.25,.35,.50,.75): add(f"ARSP{int(v*100):02d}","spread",max_entry_spread_pct=v)
for v in (2.0,3.0,4.0,5.0): add(f"ARP{int(v)}","price",min_executable_entry_price=v)
for v in (.50,.75,1.0,1.25,1.50,2.0): add(f"ARUP{int(v*100):03d}","remaining_upside",min_executable_remaining_upside_pct=v)
# Entry-known signal quality, deliberately sparse because discovery support was weaker.
for v in (1.25,1.50,2.0): add(f"ARFD{int(v*100)}","flash",min_flash_drop_pct=v)
for v in (.75,1.0,1.5): add(f"ARPR{int(v*100)}","pre_return",min_pre_return_pct=v)
# Failure management. A's target pool was profitable but STOP/EOD tails erased it.
for mins in (15,30,45,60,90,120): add(f"ARFX{mins}","fixed_time",exit_model="k_checkpoint",mode="fixed_exit",seconds=mins*60)
for mins,ret in ((30,0.0),(60,0.0),(90,0.0),(120,0.0),(60,.25),(90,.25)):
    add(f"ARR{mins}{int(ret*100):02d}","checkpoint_return",exit_model="k_checkpoint",mode="conditional_return",seconds=mins*60,min_return_pct=ret)
for mins,mfe in ((30,.20),(60,.20),(90,.20),(120,.20),(60,.40),(90,.40)):
    add(f"ARM{mins}{int(mfe*100):02d}","checkpoint_mfe",exit_model="k_checkpoint",mode="conditional_mfe",seconds=mins*60,min_mfe_pct=mfe)
for act,trail in ((.25,.15),(.25,.25),(.50,.20),(.50,.35)):
    add(f"ARAT{int(act*100):02d}{int(trail*100):02d}","adaptive_trail",exit_model="adaptive_trail_target",activation_gain_pct=act,trail_from_high_pct=trail)
for pct in (2.0,3.0,4.0): add(f"ARS{int(pct)}","stop",stop_loss_fraction=pct/100)
# Combined hypotheses. These are prospective tests, not claims that discovery P&L repeats.
add("ARXP3S50","combo",min_executable_entry_price=3.0,max_entry_spread_pct=.50)
add("ARXU15S50","combo",min_executable_remaining_upside_pct=1.5,max_entry_spread_pct=.50)
add("ARXP3U15","combo",min_executable_entry_price=3.0,min_executable_remaining_upside_pct=1.5)
add("ARXP3U15S50","combo",min_executable_entry_price=3.0,min_executable_remaining_upside_pct=1.5,max_entry_spread_pct=.50)
add("ARXP3U10S50","combo",min_executable_entry_price=3.0,min_executable_remaining_upside_pct=1.0,max_entry_spread_pct=.50)
add("ARXP3S35","combo",min_executable_entry_price=3.0,max_entry_spread_pct=.35)
add("ARXU15R60","combo",min_executable_remaining_upside_pct=1.5,exit_model="k_checkpoint",mode="conditional_return",seconds=3600,min_return_pct=0.0)
add("ARXS50R60","combo",max_entry_spread_pct=.50,exit_model="k_checkpoint",mode="conditional_return",seconds=3600,min_return_pct=0.0)
add("ARXP3U15R60","combo",min_executable_entry_price=3.0,min_executable_remaining_upside_pct=1.5,exit_model="k_checkpoint",mode="conditional_return",seconds=3600,min_return_pct=0.0)
add("ARXP3U15S3","combo",min_executable_entry_price=3.0,min_executable_remaining_upside_pct=1.5,stop_loss_fraction=.03)

IDS=frozenset(SPECS)

def config(sid):
    spec=SPECS[sid]; cfg=dict(parent.CONFIG); cfg["live_order_placement"]=False
    if "min_flash_drop_pct" in spec: cfg["flash_drop_pct"]=spec["min_flash_drop_pct"]
    return cfg

def accepts(sid,event,global_max_drop_pct):
    spec=SPECS[sid]; drop=float(event.get("flash_drop_pct") or -1)
    if not (float(spec.get("min_flash_drop_pct",1.0)) <= drop <= float(global_max_drop_pct)): return False
    if "min_pre_return_pct" in spec and float(event.get("pre_return_pct") or -1e99) < float(spec["min_pre_return_pct"]): return False
    return True

def refresh(sid,event,price):
    spec=SPECS[sid]; row=parent.refresh_event_for_entry(event,price)
    row.update(strategy_id=sid,live_order_placement=False,paper_only=True,
               forward_start_utc=BIRTH,prospective_start_utc=BIRTH,
               experimental_child=True,source_strategy_id=parent.STRATEGY_ID,
               rule_version="a_research_v2")
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
