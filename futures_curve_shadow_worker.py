"""Independent read-only Schwab worker for prospective futures-curve research."""
from __future__ import annotations
import gzip,importlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from futures_curve_paper_tracker import FuturesCurvePaperTracker

NY=ZoneInfo("America/New_York");ROOT_MONTHS={"/MES":"HMUZ","/MNQ":"HMUZ","/MCL":"FGHJKMNQUVXZ","/MGC":"GJMQVZ","/M6E":"HMUZ"};MAX_LEG_SPREAD_DOLLARS={"/MES":100.,"/MNQ":200.,"/MCL":250.,"/MGC":200.,"/M6E":50.};# Existing curve outputs disabled; continue collecting curve data.
STRATEGIES=();BASE="https://api.schwabapi.com/marketdata/v1/quotes";TOKEN_PATH=Path(os.environ.get("FUTURES_CURVE_MARKET_TOKEN","/data/schwab_token.json"));DATA_ROOT=Path(os.environ.get("FUTURES_CURVE_DATA_ROOT","/data"));POLL_SECONDS=int(os.environ.get("FUTURES_CURVE_POLL_SECONDS","300"));MAX_AGE=int(os.environ.get("FUTURES_CURVE_MAX_QUOTE_AGE","360"));STATUS=DATA_ROOT/"futures_curve_shadow_status.json"

def futures_session(now):
 et=now.astimezone(NY);w=et.weekday();m=et.hour*60+et.minute
 if w==5:return False
 if w==6:return m>=1080
 if w==4:return m<1020
 return m<1020 or m>=1080
def candidate_symbols(now):
 year=now.astimezone(NY).year;out=[]
 for root,codes in ROOT_MONTHS.items():
  for y in range(year,year+3):
   for code in codes:out.append(f"{root}{code}{y%100:02d}")
 return tuple(out)
def _token():
 obj=json.loads(TOKEN_PATH.read_text());token=obj.get("token",obj);value=token.get("access_token") if isinstance(token,dict) else None
 if not value:raise RuntimeError("market access token unavailable")
 return value
def fetch_quotes(symbols):
 out={}
 for i in range(0,len(symbols),500):
  r=requests.get(BASE,headers={"Authorization":f"Bearer {_token()}","Accept":"application/json"},params={"symbols":",".join(symbols[i:i+500])},timeout=20);r.raise_for_status();out.update(r.json())
 return out
def normalize(symbol,p):
 q=p.get("quote") or {};ref=p.get("reference") or {};return {"symbol":symbol,"realtime":p.get("realtime") is True,"bid":q.get("bidPrice"),"ask":q.get("askPrice"),"quote_time_ms":q.get("quoteTime"),"multiplier":ref.get("futureMultiplier"),"expiration_ms":ref.get("futureExpirationDate"),"active":ref.get("futureIsActive"),"description":ref.get("description")}
def fresh(q,now):
 try:return q.get("realtime") is True and float(q["bid"])>0 and float(q["ask"])>=float(q["bid"]) and float(q["multiplier"])>0 and float(q["expiration_ms"])/1000>now.timestamp() and abs(now.timestamp()-float(q["quote_time_ms"])/1000)<=MAX_AGE
 except Exception:return False
def curves(quotes):
 out={}
 for root in ROOT_MONTHS:
  rows=[]
  for q in quotes.values():
   if not q["symbol"].startswith(root):continue
   spread_dollars=(float(q["ask"])-float(q["bid"]))*float(q["multiplier"])
   if spread_dollars<=MAX_LEG_SPREAD_DOLLARS[root]:rows.append(q)
  rows.sort(key=lambda q:float(q["expiration_ms"]));out[root]=rows[:3]
 return out
def _atomic(payload):
 STATUS.parent.mkdir(parents=True,exist_ok=True);tmp=STATUS.with_suffix(".json.tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(STATUS)
def archive(now,curve):
 p=DATA_ROOT/"futures_curve_tapes"/f"curve_quotes_{now:%Y%m%d}.jsonl.gz";p.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(p,"at") as f:f.write(json.dumps({"timestamp":now.isoformat(),"curves":curve},separators=(",",":"))+"\n")
 for old in sorted(p.parent.glob("curve_quotes_*.jsonl.gz"))[:-10]:old.unlink(missing_ok=True)
def load_strategies():
 out=[]
 for sid in STRATEGIES:
  m=importlib.import_module(f"futures_curve_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())
 return out
def main():
 tracker=FuturesCurvePaperTracker(DATA_ROOT);strategies=load_strategies();decisions=errors=requests_count=0
 while True:
  started=time.monotonic();now=datetime.now(timezone.utc)
  if not futures_session(now):_atomic({"updated_at":now.isoformat(),"status":"WAITING_FUTURES_SESSION","strategies":len(strategies),"available_curves":{},"active_groups":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests_count,"broker_execution_enabled":False});time.sleep(60);continue
  try:
   requested=(*candidate_symbols(now),*tracker.required_symbols());raw=fetch_quotes(tuple(dict.fromkeys(requested)));requests_count+=(len(requested)+499)//500;normalized={s:normalize(s,p) for s,p in raw.items()};usable={s:q for s,q in normalized.items() if fresh(q,now)};curve=curves(usable);archive(now,curve);tracker.update(now,usable);found=[];snap={"timestamp":now,"curves":curve}
   for strategy in strategies:
    try:found.extend(strategy.evaluate(snap))
    except Exception:errors+=1
   tracker.open_decisions(found);decisions+=len(found);_atomic({"updated_at":now.isoformat(),"status":"RUNNING" if any(len(v)>=2 for v in curve.values()) else "WAITING_FRESH_CURVES","strategies":len(strategies),"available_curves":{k:[x["symbol"] for x in v] for k,v in curve.items()},"active_groups":len(tracker.active),"decisions":decisions,"errors":errors,"requests":requests_count,"poll_seconds":POLL_SECONDS,"broker_execution_enabled":False})
  except Exception as exc:errors+=1;_atomic({"updated_at":now.isoformat(),"status":"ERROR_BACKOFF","error":f"{type(exc).__name__}: {exc}","strategies":len(strategies),"errors":errors,"requests":requests_count,"broker_execution_enabled":False})
  time.sleep(max(1,POLL_SECONDS-(time.monotonic()-started)))
if __name__=="__main__":main()
