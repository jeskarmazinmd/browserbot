"""Isolated broad-universe Schwab worker for prospective cross-sectional research."""
from __future__ import annotations

import csv
import gzip
import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from crosssection_paper_tracker import CrossSectionPaperTracker

NY=ZoneInfo("America/New_York")
STRATEGIES=("CSRANK5","CSRANK20","CSREV1","CSVOLADJ1","CSDISP1","CSBREADTH1","CSRELSPY1","CSOPEN1")
QUOTE_URL="https://api.schwabapi.com/marketdata/v1/quotes"
TOKEN_PATH=Path(os.environ.get("CROSSSECTION_MARKET_TOKEN","/data/schwab_token.json")); DATA_ROOT=Path(os.environ.get("CROSSSECTION_DATA_ROOT","/data"))
POLL_SECONDS=float(os.environ.get("CROSSSECTION_POLL_SECONDS","60")); MAX_SYMBOLS=int(os.environ.get("CROSSSECTION_MAX_SYMBOLS","1500")); MAX_AGE=float(os.environ.get("CROSSSECTION_MAX_QUOTE_AGE_SECONDS","180")); STATUS=DATA_ROOT/"crosssection_shadow_status.json"

def regular_market(now):
    et=now.astimezone(NY); m=et.hour*60+et.minute; return et.weekday()<5 and 570<=m<960
def entry_window(now):
    et=now.astimezone(NY); m=et.hour*60+et.minute; return et.weekday()<5 and 575<=m<930
def _token():
    obj=json.loads(TOKEN_PATH.read_text()); token=obj.get("token",obj) if isinstance(obj,dict) else {}; value=token.get("access_token") if isinstance(token,dict) else None
    if not value: raise RuntimeError("market access token unavailable")
    return str(value)
def _cache_candidates(now):
    day=now.strftime("%Y%m%d"); preferred=[DATA_ROOT/f"research_universe_{day}.csv",DATA_ROOT/f"eligible_symbols_{day}.csv"]
    existing=[p for p in preferred if p.exists() and p.stat().st_size>0]
    if existing:return existing
    return sorted(list(DATA_ROOT.glob("research_universe_*.csv"))+list(DATA_ROOT.glob("eligible_symbols_*.csv")),key=lambda p:p.stat().st_mtime,reverse=True)
def load_symbols(now):
    candidates=_cache_candidates(now)
    if not candidates: raise RuntimeError("no eligible/research universe cache")
    with candidates[0].open(newline="",errors="replace") as f:
        reader=csv.DictReader(f); symbols=[]; seen=set()
        for row in reader:
            s=str(row.get("symbol") or "").upper().strip().replace(".","-")
            if s and s not in seen: seen.add(s); symbols.append(s)
    for benchmark in reversed(("SPY","QQQ")):
        if benchmark in symbols:symbols.remove(benchmark)
        symbols.insert(0,benchmark)
    if len(symbols)>MAX_SYMBOLS:
        keep=symbols[:2]; pool=symbols[2:]; needed=MAX_SYMBOLS-len(keep); step=len(pool)/needed; keep.extend(pool[min(len(pool)-1,int(i*step))] for i in range(needed)); symbols=keep
    return tuple(dict.fromkeys(symbols)),str(candidates[0])
def _batches(items,n=500):
    for i in range(0,len(items),n):yield items[i:i+n]
def fetch_quotes(symbols):
    import requests
    out={}; requests_count=0; headers={"Authorization":f"Bearer {_token()}","Accept":"application/json"}
    for batch in _batches(symbols):
        r=requests.get(QUOTE_URL,headers=headers,params={"symbols":",".join(batch)},timeout=20); requests_count+=1; r.raise_for_status(); out.update(r.json())
    return out,requests_count
def normalize(symbol,payload):
    q=payload.get("quote") or {}; return {"symbol":str(symbol).upper(),"realtime":payload.get("realtime") is True,"bid":q.get("bidPrice"),"ask":q.get("askPrice"),"last":q.get("lastPrice"),"mark":q.get("mark"),"close":q.get("closePrice"),"open":q.get("openPrice"),"quote_time_ms":q.get("quoteTime"),"total_volume":q.get("totalVolume")}
def fresh(q,now):
    try:
        bid=float(q["bid"]);ask=float(q["ask"]);age=abs(now.timestamp()-float(q["quote_time_ms"])/1000);return q.get("realtime") is True and bid>0 and ask>=bid and age<=MAX_AGE
    except Exception:return False
def _atomic(payload):
    STATUS.parent.mkdir(parents=True,exist_ok=True);tmp=STATUS.with_suffix(".json.tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(STATUS)
def archive(now,quotes):
    path=DATA_ROOT/"crosssection_tapes"/f"crosssection_quotes_{now:%Y%m%d}.jsonl.gz";path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,"at") as f:f.write(json.dumps({"timestamp":now.isoformat(),"quotes":quotes},separators=(",",":"))+"\n")
    files=sorted(path.parent.glob("crosssection_quotes_*.jsonl.gz"))
    for old in files[:-3]:old.unlink(missing_ok=True)
def load_strategies():
    result=[]
    for sid in STRATEGIES:
        m=importlib.import_module(f"crosssection_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;result.append(m.Strategy())
    return result

def main():
    tracker=CrossSectionPaperTracker(DATA_ROOT);strategies=load_strategies();symbols=();source="";loaded_day=None;decisions_total=0;errors=0;requests_total=0
    while True:
        started=time.monotonic();now=datetime.now(timezone.utc);day=now.date()
        if not regular_market(now):
            _atomic({"updated_at":now.isoformat(),"status":"WAITING_REGULAR_MARKET","strategies":len(strategies),"universe_symbols":len(symbols),"fresh_symbols":0,"decisions":decisions_total,"errors":errors,"requests":requests_total,"broker_execution_enabled":False});time.sleep(30);continue
        try:
            if loaded_day!=day:symbols,source=load_symbols(now);loaded_day=day
            raw,count=fetch_quotes(symbols);requests_total+=count;quotes={s:normalize(s,p) for s,p in raw.items() if s in symbols};usable={s:q for s,q in quotes.items() if fresh(q,now)}
            archive(now,usable);tracker.update(now,usable);decisions=[]
            if entry_window(now):
                snap={"timestamp":now,"quotes":usable}
                for strategy in strategies:
                    try:decisions.extend(strategy.evaluate(snap))
                    except Exception:errors+=1
            tracker.open_decisions(decisions);decisions_total+=len(decisions)
            _atomic({"updated_at":now.isoformat(),"status":"RUNNING" if usable else "WAITING_FRESH_QUOTES","strategies":len(strategies),"universe_symbols":len(symbols),"universe_source":source,"fresh_symbols":len(usable),"active_paper_positions":len(tracker.active),"decisions":decisions_total,"errors":errors,"requests":requests_total,"poll_seconds":POLL_SECONDS,"broker_execution_enabled":False})
        except Exception as exc:
            errors+=1;_atomic({"updated_at":now.isoformat(),"status":"ERROR_BACKOFF","error":f"{type(exc).__name__}: {exc}","strategies":len(strategies),"errors":errors,"requests":requests_total,"broker_execution_enabled":False})
        time.sleep(max(1.0,POLL_SECONDS-(time.monotonic()-started)))

if __name__=="__main__":main()
