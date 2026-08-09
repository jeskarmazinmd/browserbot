"""Independent Schwab market-data worker for prospective multi-session strategies."""
from __future__ import annotations
import gzip,importlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from swing_paper_tracker import SwingPaperTracker
NY=ZoneInfo("America/New_York")
SYMBOLS=("SPY","QQQ","IWM","DIA","XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","SMH","GLD","TLT","NVDA","AMD","AVGO","MSFT","AAPL","GOOGL","META","AMZN","TSLA")
STRATEGIES=("SWMOM2","SWMOM5","SWREV2","SWBREAK10","SWTREND20","SWREL5")
BASE="https://api.schwabapi.com/marketdata/v1";TOKEN_PATH=Path(os.environ.get("SWING_MARKET_TOKEN","/data/schwab_token.json"));DATA_ROOT=Path(os.environ.get("SWING_DATA_ROOT","/data"));POLL_SECONDS=float(os.environ.get("SWING_POLL_SECONDS","300"));STATUS=DATA_ROOT/"swing_shadow_status.json";MAX_AGE=360
def regular_market(now):
 et=now.astimezone(NY);m=et.hour*60+et.minute;return et.weekday()<5 and 570<=m<960
def entry_window(now):
 et=now.astimezone(NY);m=et.hour*60+et.minute;return et.weekday()<5 and 600<=m<900
def _token():
 obj=json.loads(TOKEN_PATH.read_text());token=obj.get("token",obj) if isinstance(obj,dict) else {};value=token.get("access_token") if isinstance(token,dict) else None
 if not value:raise RuntimeError("market access token unavailable")
 return str(value)
def _get(path,params):
 import requests
 r=requests.get(BASE+path,headers={"Authorization":f"Bearer {_token()}","Accept":"application/json"},params=params,timeout=20);r.raise_for_status();return r.json()
def fetch_history(symbol,now):
 d=_get("/pricehistory",{"symbol":symbol,"periodType":"month","period":3,"frequencyType":"daily","frequency":1,"needExtendedHoursData":"false","needPreviousClose":"true"});today=now.astimezone(NY).date();rows=[]
 for c in d.get("candles") or []:
  try:
   stamp=datetime.fromtimestamp(float(c["datetime"])/1000,tz=timezone.utc).astimezone(NY).date();close=float(c["close"])
  except Exception:continue
  if close>0 and stamp<today:rows.append((stamp.isoformat(),close))
 rows.sort();return rows[-45:]
def load_history(now):
 history={};failures={}
 for s in SYMBOLS:
  try:history[s]=fetch_history(s,now)
  except Exception as exc:failures[s]=f"{type(exc).__name__}: {exc}"
 if not any(history.values()):raise RuntimeError(f"daily history unavailable for all {len(SYMBOLS)} symbols")
 return history,failures
def fetch_quotes():return _get("/quotes",{"symbols":",".join(SYMBOLS)})
def normalize(s,p):
 q=p.get("quote") or {};return {"symbol":s,"realtime":p.get("realtime") is True,"bid":q.get("bidPrice"),"ask":q.get("askPrice"),"quote_time_ms":q.get("quoteTime")}
def fresh(q,now):
 try:
  b=float(q["bid"]);a=float(q["ask"]);age=abs(now.timestamp()-float(q["quote_time_ms"])/1000);return q.get("realtime") is True and b>0 and a>=b and age<=MAX_AGE
 except Exception:return False
def _atomic(p):
 STATUS.parent.mkdir(parents=True,exist_ok=True);tmp=STATUS.with_suffix(".json.tmp");tmp.write_text(json.dumps(p,separators=(",",":"))+"\n");tmp.replace(STATUS)
def archive(now,history,quotes):
 path=DATA_ROOT/"swing_tapes"/f"swing_snapshots_{now:%Y%m%d}.jsonl.gz";path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,"at") as f:f.write(json.dumps({"timestamp":now.isoformat(),"completed_daily_history":history,"quotes":quotes},separators=(",",":"))+"\n")
 files=sorted(path.parent.glob("swing_snapshots_*.jsonl.gz"))
 for old in files[:-10]:old.unlink(missing_ok=True)
def load_strategies():
 out=[]
 for sid in STRATEGIES:
  m=importlib.import_module(f"swing_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())
 return out
def main():
 tracker=SwingPaperTracker(DATA_ROOT);strategies=load_strategies();history={};history_failures={};loaded_day=None;decisions=0;errors=0;requests=0
 while True:
  started=time.monotonic();now=datetime.now(timezone.utc)
  if not regular_market(now):_atomic({"updated_at":now.isoformat(),"status":"WAITING_REGULAR_MARKET","strategies":len(strategies),"history_symbols":len(history),"history_failures":len(history_failures),"fresh_symbols":0,"active":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests,"broker_execution_enabled":False});time.sleep(30);continue
  try:
   today=now.astimezone(NY).date()
   if loaded_day!=today:history,history_failures=load_history(now);requests+=len(SYMBOLS);errors+=len(history_failures);loaded_day=today
   raw=fetch_quotes();requests+=1;q={s:normalize(s,p) for s,p in raw.items() if s in SYMBOLS};usable={s:x for s,x in q.items() if fresh(x,now)};archive(now,history,usable);tracker.update(now,usable);found=[]
   if entry_window(now):
    snap={"timestamp":now,"completed_daily_history":history,"quotes":usable}
    for strategy in strategies:
     try:found.extend(strategy.evaluate(snap))
     except Exception:errors+=1
   tracker.open_decisions(found);decisions+=len(found);_atomic({"updated_at":now.isoformat(),"status":"RUNNING" if usable else "WAITING_FRESH_QUOTES","strategies":len(strategies),"history_symbols":sum(bool(v) for v in history.values()),"history_failures":len(history_failures),"fresh_symbols":len(usable),"active":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests,"poll_seconds":POLL_SECONDS,"broker_execution_enabled":False})
  except Exception as exc:errors+=1;_atomic({"updated_at":now.isoformat(),"status":"ERROR_BACKOFF","error":f"{type(exc).__name__}: {exc}","strategies":len(strategies),"errors":errors,"requests":requests,"broker_execution_enabled":False})
  time.sleep(max(1.0,POLL_SECONDS-(time.monotonic()-started)))
if __name__=="__main__":main()
