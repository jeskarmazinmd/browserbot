"""Independent Schwab market-data worker for prospective multi-session strategies."""
from __future__ import annotations
import csv,gzip,hashlib,importlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from swing_paper_tracker import SwingPaperTracker
NY=ZoneInfo("America/New_York")
ANCHORS=("SPY","QQQ","IWM","DIA","XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","SMH","GLD","TLT","NVDA","AMD","AVGO","MSFT","AAPL","GOOGL","META","AMZN","TSLA")
STRATEGIES=("SWREV2","SWTREND20")
BASE="https://api.schwabapi.com/marketdata/v1";TOKEN_PATH=Path(os.environ.get("SWING_MARKET_TOKEN","/data/schwab_token.json"));DATA_ROOT=Path(os.environ.get("SWING_DATA_ROOT","/data"));POLL_SECONDS=float(os.environ.get("SWING_POLL_SECONDS","300"));STATUS=DATA_ROOT/"swing_shadow_status.json";MAX_AGE=360;UNIVERSE_LIMIT=int(os.environ.get("SWING_UNIVERSE_LIMIT","500"));HISTORY_PACE_SECONDS=float(os.environ.get("SWING_HISTORY_PACE_SECONDS","0.25"))
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
def universe_path(now):
 day=now.astimezone(NY).strftime("%Y%m%d");preferred=(DATA_ROOT/f"research_universe_{day}.csv",DATA_ROOT/f"eligible_symbols_{day}.csv")
 for p in preferred:
  if p.exists() and p.stat().st_size:return p
 candidates=sorted([*DATA_ROOT.glob("research_universe_*.csv"),*DATA_ROOT.glob("eligible_symbols_*.csv")],key=lambda p:p.stat().st_mtime,reverse=True)
 return candidates[0] if candidates else None
def load_universe(now):
 p=universe_path(now);symbols=[]
 if p is not None:
  with p.open(newline="",errors="replace") as f:
   for row in csv.DictReader(f):
    s=str(row.get("symbol") or "").strip().upper().replace(".","-")
    if s and s not in symbols:symbols.append(s)
 # Stable hash selection avoids an alphabetically biased first-N universe.
 ranked=sorted(symbols,key=lambda s:hashlib.sha256(f"SWING6|{s}".encode()).digest())
 wanted=[]
 for s in (*ANCHORS,*ranked):
  if s not in wanted:wanted.append(s)
 return tuple(wanted[:max(len(ANCHORS),UNIVERSE_LIMIT)])
def fetch_history(symbol,now):
 d=_get("/pricehistory",{"symbol":symbol,"periodType":"month","period":3,"frequencyType":"daily","frequency":1,"needExtendedHoursData":"false","needPreviousClose":"true"});today=now.astimezone(NY).date();rows=[]
 for c in d.get("candles") or []:
  try:
   stamp=datetime.fromtimestamp(float(c["datetime"])/1000,tz=timezone.utc).astimezone(NY).date();close=float(c["close"])
  except Exception:continue
  if close>0 and stamp<today:rows.append((stamp.isoformat(),close))
 rows.sort();return rows[-45:]
def history_cache_path(now):return DATA_ROOT/f"swing_daily_history_{now.astimezone(NY):%Y%m%d}.json"
def _save_history_cache(now,history,failures):
 p=history_cache_path(now);payload={"market_date":now.astimezone(NY).date().isoformat(),"history":history,"failures":failures};tmp=p.with_suffix(".json.tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(p)
 for old in sorted(DATA_ROOT.glob("swing_daily_history_*.json"))[:-3]:old.unlink(missing_ok=True)
def load_history(now,symbols):
 cache=history_cache_path(now)
 if cache.exists():
  try:
   saved=json.loads(cache.read_text());history=saved.get("history") or {};failures=saved.get("failures") or {}
   if history:return history,failures,0
  except Exception:pass
 history={};failures={}
 for i,s in enumerate(symbols):
  try:history[s]=fetch_history(s,now)
  except Exception as exc:failures[s]=f"{type(exc).__name__}: {exc}"
  if i+1<len(symbols) and HISTORY_PACE_SECONDS>0:time.sleep(HISTORY_PACE_SECONDS)
 if not any(history.values()):raise RuntimeError(f"daily history unavailable for all {len(symbols)} symbols")
 _save_history_cache(now,history,failures);return history,failures,len(symbols)
def fetch_quotes(symbols):
 out={}
 for i in range(0,len(symbols),500):out.update(_get("/quotes",{"symbols":",".join(symbols[i:i+500])}))
 return out
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
 tracker=SwingPaperTracker(DATA_ROOT);strategies=load_strategies();symbols=ANCHORS;history={};history_failures={};loaded_day=None;decisions=0;errors=0;requests=0
 while True:
  started=time.monotonic();now=datetime.now(timezone.utc)
  if not regular_market(now):_atomic({"updated_at":now.isoformat(),"status":"WAITING_REGULAR_MARKET","strategies":len(strategies),"universe_symbols":len(symbols),"history_symbols":len(history),"history_failures":len(history_failures),"fresh_symbols":0,"active":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests,"broker_execution_enabled":False});time.sleep(30);continue
  try:
   today=now.astimezone(NY).date()
   if loaded_day!=today:symbols=load_universe(now);history,history_failures,used=load_history(now,symbols);requests+=used;errors+=len(history_failures);loaded_day=today
   raw=fetch_quotes(symbols);requests+=(len(symbols)+499)//500;q={s:normalize(s,p) for s,p in raw.items() if s in symbols};usable={s:x for s,x in q.items() if fresh(x,now)};archive(now,history,usable);tracker.update(now,usable);found=[]
   if entry_window(now):
    snap={"timestamp":now,"completed_daily_history":history,"quotes":usable}
    for strategy in strategies:
     try:found.extend(strategy.evaluate(snap))
     except Exception:errors+=1
   tracker.open_decisions(found);decisions+=len(found);_atomic({"updated_at":now.isoformat(),"status":"RUNNING" if usable else "WAITING_FRESH_QUOTES","strategies":len(strategies),"universe_symbols":len(symbols),"history_symbols":sum(bool(v) for v in history.values()),"history_failures":len(history_failures),"fresh_symbols":len(usable),"active":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests,"poll_seconds":POLL_SECONDS,"history_cache":str(history_cache_path(now)),"broker_execution_enabled":False})
  except Exception as exc:errors+=1;_atomic({"updated_at":now.isoformat(),"status":"ERROR_BACKOFF","error":f"{type(exc).__name__}: {exc}","strategies":len(strategies),"errors":errors,"requests":requests,"broker_execution_enabled":False})
  time.sleep(max(1.0,POLL_SECONDS-(time.monotonic()-started)))
if __name__=="__main__":main()
