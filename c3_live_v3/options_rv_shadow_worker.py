"""Isolated, read-only Schwab chain worker for Options Relative Value6."""
from __future__ import annotations

import gzip
import importlib
import json
import os
import signal
import time
from datetime import datetime, time as clock, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:  # lets wiring tests import without optional networking deps
    requests = None

from options_rv_paper_tracker import OptionsRVTracker

UNDERLYINGS=("SPY","QQQ","IWM")
STRATEGIES=("rvputcr1","rvcallcr1","rvcond1","rvcal1","rvdiag1","rvfly1")
POLL_SECONDS=float(os.getenv("OPTIONS_RV_POLL_SECONDS","300"))
DATA_ROOT=Path(os.getenv("DATA_ROOT","/data"))
STATUS=DATA_ROOT/"options_rv_shadow_status.json"
ARCHIVE=DATA_ROOT/"options_rv_tapes"
TOKEN=DATA_ROOT/"schwab_token.json"
NY=ZoneInfo("America/New_York")
RUNNING=True

def regular_market(now):
    local=now.astimezone(NY)
    return local.weekday()<5 and clock(9,30)<=local.time()<=clock(16,0)

def load_strategies():
    result=[]
    for name in STRATEGIES:
        module=importlib.import_module(f"options_rv_strategies.strategy_{name}")
        if not module.PAPER_ONLY or module.LIVE_ORDER_PLACEMENT:
            raise RuntimeError(f"unsafe options RV module: {module.NAME}")
        result.append(module)
    return result

def access_token():
    value=json.loads(TOKEN.read_text())
    return value.get("token",value)["access_token"]

def fetch_chain(symbol,now):
    if requests is None: raise RuntimeError("requests unavailable")
    response=requests.get(
        "https://api.schwabapi.com/marketdata/v1/chains",
        headers={"Authorization":f"Bearer {access_token()}","Accept":"application/json"},
        params={"symbol":symbol,"contractType":"ALL","strikeCount":20,
                "includeUnderlyingQuote":"true","fromDate":str((now+timedelta(days=7)).date()),
                "toDate":str((now+timedelta(days=50)).date())},timeout=25,
    )
    response.raise_for_status()
    return response.json()

def contracts(payload):
    rows=[]
    for section in ("callExpDateMap","putExpDateMap"):
        for strikes in payload.get(section,{ }).values():
            for values in strikes.values():
                for x in values:
                    try:dte=int(x.get("daysToExpiration",-1))
                    except (TypeError,ValueError):continue
                    if not 7<=dte<=50:continue
                    row={k:x.get(k) for k in (
                        "symbol","description","putCall","bid","ask","last","mark",
                        "bidSize","askSize","totalVolume","openInterest","volatility",
                        "delta","gamma","theta","vega","rho","strikePrice",
                        "daysToExpiration","expirationDate","inTheMoney","intrinsicValue",
                        "timeValue","multiplier","quoteTimeInLong","tradeTimeInLong")}
                    row["underlyingPrice"]=payload.get("underlyingPrice")
                    rows.append(row)
    return rows

def _atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,separators=(",",":")));tmp.replace(path)

def archive(now,symbol,rows):
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    path=ARCHIVE/f"options_rv_{now:%Y%m%d}.jsonl.gz"
    with gzip.open(path,"at") as handle:
        handle.write(json.dumps({"timestamp":now.isoformat(),"underlying":symbol,"contracts":rows},separators=(",",":"))+"\n")

def status(now,state,strategies,tracker,requests_count=0,decisions=0,errors=0,fresh=0):
    _atomic(STATUS,{"updated_at":now.isoformat(),"status":state,"strategies":len(strategies),
        "underlyings":list(UNDERLYINGS),"fresh_underlyings":fresh,
        "active_paper_groups":len(tracker.active),"decisions":decisions,"errors":errors,
        "requests":requests_count,"poll_seconds":POLL_SECONDS,"broker_execution_enabled":False})

def run_once(now,strategies,tracker):
    all_quotes={};requests_count=0;decisions=0;errors=0;fresh=0
    for symbol in UNDERLYINGS:
        try:
            payload=fetch_chain(symbol,now);requests_count+=1;rows=contracts(payload)
            if rows:fresh+=1
            archive(now,symbol,rows)
            all_quotes.update({x["symbol"]:x for x in rows if x.get("symbol")})
            for strategy in strategies:
                try:
                    signal_value=strategy.evaluate(symbol,rows,now)
                    if signal_value and tracker.open(signal_value,now):decisions+=1
                except Exception:errors+=1
        except Exception:errors+=1
    tracker.update(all_quotes,now)
    status(now,"RUNNING",strategies,tracker,requests_count,decisions,errors,fresh)

def main():
    DATA_ROOT.mkdir(parents=True,exist_ok=True);strategies=load_strategies();tracker=OptionsRVTracker(DATA_ROOT)
    while RUNNING:
        now=datetime.now(timezone.utc)
        if regular_market(now):run_once(now,strategies,tracker)
        else:status(now,"WAITING_REGULAR_MARKET",strategies,tracker)
        time.sleep(POLL_SECONDS)

def _stop(*_):
    global RUNNING;RUNNING=False

if __name__=="__main__":
    signal.signal(signal.SIGTERM,_stop);signal.signal(signal.SIGINT,_stop);main()
