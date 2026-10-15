"""Isolated read-only Schwab worker for dynamic statistical-arbitrage research."""
from __future__ import annotations
import gzip,importlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from statarb_paper_tracker import StatArbPaperTracker
from generation_nine_paper_tracker import GenerationNineTracker, FILE_STEM as G9_FILE_STEM
from strategies import generation_nine as g9
from strategies.pruning import active_output_ids

NY=ZoneInfo("America/New_York")
SYMBOLS=("SPY","QQQ","IWM","DIA","XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLC","SMH","IYT","GLD","SLV","USO","TLT","NVDA","AMD","AVGO","MSFT","AAPL","GOOGL","META","AMZN","TSLA","NFLX","ORCL","CRM","MU","INTC","JPM","BAC","GS","WMT")
STRATEGIES=active_output_ids(("STBETA1","STPAIR1","STSECTOR1","STBREAK1","STRESMOM1"))
STRATEGIES2=active_output_ids(("STCINT2","STHEDGE2","STLEAD2"))
QUOTE_URL="https://api.schwabapi.com/marketdata/v1/quotes";TOKEN_PATH=Path(os.environ.get("STATARB_MARKET_TOKEN","/data/schwab_token.json"));DATA_ROOT=Path(os.environ.get("STATARB_DATA_ROOT","/data"));POLL_SECONDS=float(os.environ.get("STATARB_POLL_SECONDS","60"));MAX_AGE=float(os.environ.get("STATARB_MAX_QUOTE_AGE_SECONDS","5"));STATUS=DATA_ROOT/"statarb_shadow_status.json"
def regular_market(now):
 et=now.astimezone(NY);m=et.hour*60+et.minute;return et.weekday()<5 and 570<=m<960
def entry_window(now):
 et=now.astimezone(NY);m=et.hour*60+et.minute;return et.weekday()<5 and 575<=m<930
def _token():
 obj=json.loads(TOKEN_PATH.read_text());token=obj.get("token",obj) if isinstance(obj,dict) else {};value=token.get("access_token") if isinstance(token,dict) else None
 if not value:raise RuntimeError("market access token unavailable")
 return str(value)
def fetch_quotes():
 import requests
 r=requests.get(QUOTE_URL,headers={"Authorization":f"Bearer {_token()}","Accept":"application/json"},params={"symbols":",".join(SYMBOLS)},timeout=20);r.raise_for_status();return r.json()
def normalize(symbol,payload):
 q=payload.get("quote") or {};return {"symbol":str(symbol).upper(),"realtime":payload.get("realtime") is True,"bid":q.get("bidPrice"),"ask":q.get("askPrice"),"last":q.get("lastPrice"),"quote_time_ms":q.get("quoteTime"),"bid_time_ms":q.get("bidTime",q.get("quoteTime")),"ask_time_ms":q.get("askTime",q.get("quoteTime")),"bid_size_raw":q.get("bidSize"),"ask_size_raw":q.get("askSize")}
def fresh(q,now):
 try:
  b=float(q["bid"]);a=float(q["ask"]);age=abs(now.timestamp()-float(q["quote_time_ms"])/1000);return q.get("realtime") is True and b>0 and a>=b and age<=MAX_AGE
 except Exception:return False
def _atomic(payload):
 STATUS.parent.mkdir(parents=True,exist_ok=True);tmp=STATUS.with_suffix(".json.tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(STATUS)
def archive(now,quotes):
 path=DATA_ROOT/"statarb_tapes"/f"statarb_quotes_{now:%Y%m%d}.jsonl.gz";path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,"at") as f:f.write(json.dumps({"timestamp":now.isoformat(),"quotes":quotes},separators=(",",":"))+"\n")
 files=sorted(path.parent.glob("statarb_quotes_*.jsonl.gz"))
 for old in files[:-5]:old.unlink(missing_ok=True)
def load_strategies():
 out=[]
 for package,ids in (("statarb_strategies",STRATEGIES),("statarb2_strategies",STRATEGIES2)):
  for sid in ids:
   m=importlib.import_module(f"{package}.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())
 return out
def g9_cycle(tracker,population,now,quotes):
 if tracker is None:return
 observed=population.observe(now,quotes)
 tracker.update(quotes,now,population)
 if observed and os.environ.get('ENABLE_G9_PAPER','0')=='1':
  for spec in g9.CATALOG:
   if spec.strategy_id in tracker.active:continue
   last=tracker.last.get(spec.strategy_id)
   if last and (now-last).total_seconds()<spec.cooldown_minutes*60:continue
   decision=population.decision(spec,now)
   if decision:tracker.open(decision,quotes,now)
 tracker.status()

def main():
 tracker=StatArbPaperTracker(DATA_ROOT);strategies=load_strategies();decisions_total=0;errors=0;requests_total=0
 g9_tracker=GenerationNineTracker(DATA_ROOT) if os.environ.get('ENABLE_G9_PAPER','0')=='1' or (DATA_ROOT/(G9_FILE_STEM+'_births.json')).exists() else None
 g9_population=g9.Population()
 while True:
  started=time.monotonic();now=datetime.now(timezone.utc)
  if not regular_market(now):
   _atomic({"updated_at":now.isoformat(),"status":"WAITING_REGULAR_MARKET","strategies":len(strategies),"symbols":len(SYMBOLS),"fresh_symbols":0,"active_paper_groups":len(tracker.active),"decisions":decisions_total,"errors":errors,"requests":requests_total,"broker_execution_enabled":False});time.sleep(30);continue
  try:
   raw=fetch_quotes();now=datetime.now(timezone.utc);requests_total+=1;quotes={s:normalize(s,p) for s,p in raw.items() if s in SYMBOLS};usable={s:q for s,q in quotes.items() if fresh(q,now)};archive(now,usable);tracker.update(now,usable);g9_cycle(g9_tracker,g9_population,now,quotes);decisions=[]
   if entry_window(now):
    snap={"timestamp":now,"quotes":usable}
    for strategy in strategies:
     try:decisions.extend(strategy.evaluate(snap))
     except Exception:errors+=1
   tracker.open_decisions(decisions);decisions_total+=len(decisions);_atomic({"updated_at":now.isoformat(),"status":"RUNNING" if usable else "WAITING_FRESH_QUOTES","strategies":len(strategies),"symbols":len(SYMBOLS),"fresh_symbols":len(usable),"active_paper_groups":len(tracker.active),"decisions":decisions_total,"errors":errors,"requests":requests_total,"poll_seconds":POLL_SECONDS,"broker_execution_enabled":False})
  except Exception as exc:
   errors+=1;_atomic({"updated_at":now.isoformat(),"status":"ERROR_BACKOFF","error":f"{type(exc).__name__}: {exc}","strategies":len(strategies),"errors":errors,"requests":requests_total,"broker_execution_enabled":False})
  time.sleep(max(1.0,POLL_SECONDS-(time.monotonic()-started)))
if __name__=="__main__":main()
