"""Persistent spread-aware paper accounting for futures calendar strategies."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path

COMMISSION_PER_CONTRACT_SIDE=2.25

def _dt(value):
 if isinstance(value,datetime):return value.astimezone(timezone.utc)
 return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)
def _atomic(path,payload):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(path)

class FuturesCurvePaperTracker:
 def __init__(self,root="/data"):
  self.root=Path(root);self.ledger=self.root/"futures_curve_paper_outcomes.jsonl";self.status_path=self.root/"futures_curve_paper_status.json";self.active={};self.seen=set();self.completed=0;self._restore();self._status()
 def _restore(self):
  if not self.ledger.exists():return
  try:
   for line in self.ledger.read_text(errors="replace").splitlines():
    try:r=json.loads(line)
    except Exception:continue
    key=r.get("group_id")
    if not key:continue
    self.seen.add(key)
    if r.get("event")=="OPEN":self.active[key]=r
    elif r.get("event")=="CLOSE":self.active.pop(key,None);self.completed+=1
  except OSError:pass
 def _append(self,row):
  self.ledger.parent.mkdir(parents=True,exist_ok=True)
  with self.ledger.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
 def _status(self):
  _atomic(self.status_path,{"updated_at":datetime.now(timezone.utc).isoformat(),"active_groups":len(self.active),"completed_groups":self.completed,"seen_groups":len(self.seen),"contracts_per_leg":1,"commission_per_contract_side":COMMISSION_PER_CONTRACT_SIDE,"exchange_regulatory_fees_included":False,"initial_maintenance_margin_modeled":False,"variation_margin_modeled":False,"roll_execution_modeled":True,"broker_execution_enabled":False,"pricing":"LONG open@ask close@bid; SHORT open@bid close@ask; both calendar legs cross spread"})
 def required_symbols(self):return sorted({leg["symbol"] for group in self.active.values() for leg in group["legs"]})
 def open_decisions(self,decisions):
  opened=0
  for d in decisions:
   now=_dt(d["timestamp"]);legs=[];bad=False
   for leg in d.get("legs",[]):
    side=str(leg.get("side","")).upper();bid=float(leg.get("bid") or 0);ask=float(leg.get("ask") or 0);mult=float(leg.get("multiplier") or 0)
    if side not in {"LONG","SHORT"} or bid<=0 or ask<bid or mult<=0:bad=True;break
    item=dict(leg);item["entry_price"]=ask if side=="LONG" else bid;item["entry_commission"]=COMMISSION_PER_CONTRACT_SIDE;legs.append(item)
   if bad or len(legs)!=2:continue
   key="|".join([d["strategy_id"],now.date().isoformat()]+[x["symbol"]+":"+x["side"] for x in legs])
   if key in self.seen:continue
   row={"event":"OPEN","group_id":key,"strategy_id":d["strategy_id"],"opened_at":now.isoformat(),"legs":legs,"take_profit_dollars":float(d["take_profit_dollars"]),"stop_loss_dollars":float(d["stop_loss_dollars"]),"max_hold_minutes":int(d["max_hold_minutes"]),"research":d.get("research",{}),"paper_only":True,"broker_execution_enabled":False};self.active[key]=row;self.seen.add(key);self._append(row);opened+=1
  self._status();return opened
 @staticmethod
 def _pnl(group,quotes):
  total=0.;closes=[]
  for leg in group["legs"]:
   q=quotes.get(leg["symbol"])
   if not q:return None,None
   bid=float(q.get("bid") or 0);ask=float(q.get("ask") or 0)
   if bid<=0 or ask<bid:return None,None
   if leg["side"]=="LONG":close=bid;gross=(close-leg["entry_price"])*leg["multiplier"]
   else:close=ask;gross=(leg["entry_price"]-close)*leg["multiplier"]
   net=gross-leg["entry_commission"]-COMMISSION_PER_CONTRACT_SIDE;total+=net;closes.append({"symbol":leg["symbol"],"close_price":close,"gross_pnl_dollars":gross,"net_pnl_dollars":net})
  return total,closes
 def update(self,timestamp,quotes):
  now=_dt(timestamp);closing=[]
  for key,g in list(self.active.items()):
   pnl,legs=self._pnl(g,quotes)
   if pnl is None:continue
   age=(now-_dt(g["opened_at"])).total_seconds()/60;reason="TARGET" if pnl>=g["take_profit_dollars"] else ("STOP" if pnl<=-g["stop_loss_dollars"] else ("TIMEOUT" if age>=g["max_hold_minutes"] else None))
   if reason:closing.append((key,g,pnl,legs,reason))
  for key,g,pnl,legs,reason in closing:
   self._append({"event":"CLOSE","group_id":key,"strategy_id":g["strategy_id"],"opened_at":g["opened_at"],"closed_at":now.isoformat(),"reason":reason,"net_pnl_dollars":pnl,"legs":legs,"paper_only":True,"broker_execution_enabled":False});self.active.pop(key,None);self.completed+=1
  self._status();return len(closing)
