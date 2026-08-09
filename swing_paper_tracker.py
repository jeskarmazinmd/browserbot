"""Persistent multi-session paper accounting for prospective swing research."""
from __future__ import annotations
import json
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
NY=ZoneInfo("America/New_York")
def _dt(x):
 if isinstance(x,datetime):return x.astimezone(timezone.utc)
 return datetime.fromisoformat(str(x).replace("Z","+00:00")).astimezone(timezone.utc)
def _atomic(path,p):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(p,separators=(",",":"))+"\n");tmp.replace(path)
def _weekday_sessions(start,end):
 cur=start;n=0
 while cur<=end:
  if cur.weekday()<5:n+=1
  cur+=timedelta(days=1)
 return n
class SwingPaperTracker:
 def __init__(self,root="/data",notional=1000.0):
  self.root=Path(root);self.notional=float(notional);self.ledger=self.root/"swing_paper_outcomes.jsonl";self.status_path=self.root/"swing_paper_status.json";self.active={};self.seen=set();self.completed=0;self._restore();self._status()
 def _restore(self):
  if not self.ledger.exists():return
  try:
   for line in self.ledger.read_text(errors="replace").splitlines():
    try:r=json.loads(line)
    except Exception:continue
    key=r.get("setup_id")
    if not key:continue
    self.seen.add(key)
    if r.get("event")=="OPEN":self.active[key]=r
    elif r.get("event")=="CLOSE":self.active.pop(key,None);self.completed+=1
  except OSError:pass
 def _append(self,r):
  self.ledger.parent.mkdir(parents=True,exist_ok=True)
  with self.ledger.open("a") as f:f.write(json.dumps(r,separators=(",",":"))+"\n")
 def _status(self):
  _atomic(self.status_path,{"updated_at":datetime.now(timezone.utc).isoformat(),"active":len(self.active),"completed":self.completed,"seen":len(self.seen),"notional_per_signal":self.notional,"broker_execution_enabled":False,"bid_ask_spread_included":True,"overnight_financing_included":False,"dividends_corporate_actions_modeled":False,"market_holiday_calendar_modeled":False,"borrow_fees_included":False,"short_locate_verified":False,"pricing":"LONG open@ask close@bid; SHORT open@bid close@ask; whole shares; positions may span sessions"})
 def open_decisions(self,decisions):
  opened=0
  for d in decisions:
   side=str(d.get("side","")).upper();now=_dt(d["timestamp"]);s=str(d.get("symbol","")).upper();bid=float(d.get("bid") or 0);ask=float(d.get("ask") or 0)
   if side not in {"LONG","SHORT"} or not s or bid<=0 or ask<bid:continue
   entry=ask if side=="LONG" else bid;shares=int(self.notional/entry)
   if shares<1:continue
   market_date=now.astimezone(NY).date();key=f'{d["strategy_id"]}|{s}|{market_date.isoformat()}'
   if key in self.seen:continue
   tp=float(d["target_pct"]);sp=float(d["stop_pct"]);row={"event":"OPEN","setup_id":key,"strategy_id":d["strategy_id"],"symbol":s,"side":side,"opened_at":now.isoformat(),"opened_market_date":market_date.isoformat(),"entry_price":entry,"entry_bid":bid,"entry_ask":ask,"shares":shares,"notional_used":shares*entry,"target_price":entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100),"stop_price":entry*(1-sp/100) if side=="LONG" else entry*(1+sp/100),"max_hold_sessions":int(d["max_hold_sessions"]),"research":d.get("research",{}),"paper_only":True,"broker_execution_enabled":False};self.active[key]=row;self.seen.add(key);self._append(row);opened+=1
  self._status();return opened
 def update(self,timestamp,quotes):
  now=_dt(timestamp);et=now.astimezone(NY);today=et.date();near_close=(et.hour,et.minute)>=(15,50);closing=[]
  for key,row in list(self.active.items()):
   q=quotes.get(row["symbol"])
   if not q:continue
   bid=float(q.get("bid") or 0);ask=float(q.get("ask") or 0)
   if bid<=0 or ask<bid:continue
   exit_price=bid if row["side"]=="LONG" else ask;reason=None
   if row["side"]=="LONG":
    if exit_price>=row["target_price"]:reason="TARGET"
    elif exit_price<=row["stop_price"]:reason="STOP"
   else:
    if exit_price<=row["target_price"]:reason="TARGET"
    elif exit_price>=row["stop_price"]:reason="STOP"
   sessions=_weekday_sessions(date.fromisoformat(row["opened_market_date"]),today)
   if reason is None and near_close and sessions>=row["max_hold_sessions"]:reason="MAX_SESSIONS"
   if reason:closing.append((key,row,exit_price,bid,ask,reason,sessions))
  for key,row,exit_price,bid,ask,reason,sessions in closing:
   sign=1 if row["side"]=="LONG" else -1;pnl=sign*(exit_price-row["entry_price"])*row["shares"];ret=sign*(exit_price-row["entry_price"])/row["entry_price"]*100;self._append({"event":"CLOSE","setup_id":key,"strategy_id":row["strategy_id"],"symbol":row["symbol"],"side":row["side"],"opened_at":row["opened_at"],"closed_at":now.isoformat(),"sessions_held":sessions,"entry_price":row["entry_price"],"exit_price":exit_price,"exit_bid":bid,"exit_ask":ask,"shares":row["shares"],"exit_reason":reason,"return_pct":ret,"pnl":pnl,"overnight_financing_included":False,"dividends_corporate_actions_modeled":False,"borrow_fees_included":False,"paper_only":True,"broker_execution_enabled":False});self.active.pop(key,None);self.completed+=1
  self._status();return len(closing)
