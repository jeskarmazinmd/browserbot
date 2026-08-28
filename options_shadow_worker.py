"""Isolated prospective options market-data + strategy worker. No trading client."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone,time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo
import gzip,importlib,json,os,time
import requests

from options_paper_tracker import OptionsPaperTracker

NY=ZoneInfo("America/New_York")
UNDERLYINGS=("SPY","QQQ","IWM","AAPL","NVDA","TSLA")
# Failed strategy outputs disabled 2026-08-28. Keep collecting option-chain
# tapes so replacement strategies can be researched against forward data.
STRATEGIES=()
POLL_SECONDS=float(os.environ.get("OPTIONS_POLL_SECONDS","120"))
DATA_ROOT=Path(os.environ.get("OPTIONS_DATA_ROOT","/data"))
STATUS=DATA_ROOT/"options_shadow_status.json"
TOKEN_PATH=Path(os.environ.get("OPTIONS_MARKET_TOKEN","/data/schwab_token.json"))
CHAIN_URL="https://api.schwabapi.com/marketdata/v1/chains"
FIELDS=("symbol","description","putCall","bid","ask","last","mark","bidSize","askSize","lastSize","totalVolume","openInterest","volatility","delta","gamma","theta","vega","rho","strikePrice","daysToExpiration","expirationDate","inTheMoney","intrinsicValue","timeValue","multiplier","quoteTimeInLong","tradeTimeInLong")

def _regular(now):
    x=now.astimezone(NY);return x.weekday()<5 and clock_time(9,30)<=x.time()<clock_time(16,0)
def _atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(payload,separators=(",",":"),default=str)+"\n");os.replace(tmp,path)
def _contracts(data):
    rows=[]
    for mapname in ("callExpDateMap","putExpDateMap"):
        for expiration in (data.get(mapname) or {}).values():
            for contracts in expiration.values():
                for c in contracts or []:
                    d=int(c.get("daysToExpiration") or -1)
                    if 7<=d<=45:rows.append({k:c.get(k) for k in FIELDS if k in c})
    return rows
def _snapshot(symbol,data,now):
    return {"timestamp":now.isoformat(),"underlying":symbol,"underlyingPrice":data.get("underlyingPrice"),"isDelayed":data.get("isDelayed"),"status":data.get("status"),"contracts":_contracts(data)}
def _archive(snapshot):
    day=datetime.fromisoformat(snapshot["timestamp"]).strftime("%Y%m%d");path=DATA_ROOT/"options_tapes"/f"option_chains_{day}.jsonl.gz";path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,"at") as f:f.write(json.dumps(snapshot,separators=(",",":"),default=str)+"\n")
def _access_token():
    obj=json.loads(TOKEN_PATH.read_text());token=obj.get("token",obj) if isinstance(obj,dict) else {}
    value=token.get("access_token") if isinstance(token,dict) else None
    if not value:raise RuntimeError("market access token unavailable")
    return str(value)
def _fetch_chain(symbol,now):
    # Deliberately never refreshes or writes OAuth state. The production market
    # client owns token refresh; this optional worker is a read-only consumer.
    response=requests.get(CHAIN_URL,headers={"Authorization":f"Bearer {_access_token()}","Accept":"application/json"},params={"symbol":symbol,"strikeCount":5,"includeUnderlyingQuote":"true","fromDate":str(now.date()+timedelta(days=7)),"toDate":str(now.date()+timedelta(days=45))},timeout=20)
    if response.status_code!=200:raise RuntimeError(f"{symbol} HTTP {response.status_code}")
    return response.json()
def _load_strategies():
    return [importlib.import_module(f"options_strategies.strategy_{sid.lower()}").Strategy() for sid in STRATEGIES]

def main():
    strategies=_load_strategies();tracker=OptionsPaperTracker(DATA_ROOT);decisions=0;errors=0
    print(f"OPTIONS_SHADOW starting strategies={len(strategies)} underlyings={len(UNDERLYINGS)}",flush=True)
    while True:
        now=datetime.now(timezone.utc)
        if not _regular(now):
            _atomic(STATUS,{"updated_at":now.isoformat(),"status":"WAITING_REGULAR_MARKET","strategies":len(strategies),"broker_execution_enabled":False});time.sleep(30);continue
        cycle_errors=[];delayed=[];contracts_total=0
        for symbol in UNDERLYINGS:
            try:
                snap=_snapshot(symbol,_fetch_chain(symbol,now),now);contracts_total+=len(snap["contracts"]);_archive(snap);tracker.update(snap)
                if snap.get("isDelayed") is True:delayed.append(symbol);continue
                for strategy in strategies:
                    for decision in strategy.evaluate(snap):
                        if tracker.register(decision):decisions+=1
            except Exception as exc:
                errors+=1;cycle_errors.append(f"{symbol}:{type(exc).__name__}:{exc}")
        _atomic(STATUS,{"updated_at":datetime.now(timezone.utc).isoformat(),"status":"RUNNING" if not cycle_errors else "DEGRADED","strategies":len(strategies),"underlyings":len(UNDERLYINGS),"contracts":contracts_total,"decisions_total":decisions,"errors_total":errors,"cycle_errors":cycle_errors,"delayed":delayed,"broker_execution_enabled":False,"poll_seconds":POLL_SECONDS})
        time.sleep(POLL_SECONDS)

if __name__=="__main__":main()
