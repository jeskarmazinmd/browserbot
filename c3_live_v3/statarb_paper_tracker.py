"""Conservative grouped paper accounting for dynamic statistical-arbitrage research."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
NY=ZoneInfo("America/New_York")

def _dt(x):
    if isinstance(x,datetime):return x.astimezone(timezone.utc)
    return datetime.fromisoformat(str(x).replace("Z","+00:00")).astimezone(timezone.utc)
def _atomic(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");tmp.replace(path)

class StatArbPaperTracker:
    def __init__(self,root="/data",group_notional=5000.0):
        self.root=Path(root);self.group_notional=float(group_notional);self.ledger=self.root/"statarb_paper_outcomes.jsonl";self.status_path=self.root/"statarb_paper_status.json";self.active={};self.seen=set();self.completed=0;self._restore();self._status()
    def _restore(self):
        if not self.ledger.exists():return
        try:
            for line in self.ledger.read_text(errors="replace").splitlines():
                try:r=json.loads(line)
                except Exception:continue
                gid=r.get("group_id")
                if not gid:continue
                self.seen.add(gid)
                if r.get("event")=="OPEN":self.active[gid]=r
                elif r.get("event")=="CLOSE":self.active.pop(gid,None);self.completed+=1
        except OSError:pass
    def _append(self,row):
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        with self.ledger.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
    def _status(self):
        _atomic(self.status_path,{"updated_at":datetime.now(timezone.utc).isoformat(),"active_groups":len(self.active),"completed_groups":self.completed,"seen_groups":len(self.seen),"group_gross_notional":self.group_notional,"broker_execution_enabled":False,"bid_ask_spread_included":True,"borrow_fees_included":False,"short_locate_verified":False,"pricing":"LONG open@ask close@bid; SHORT open@bid close@ask; whole shares"})
    def open_decisions(self,decisions):
        opened=0
        for d in decisions:
            now=_dt(d["timestamp"]);raw=list(d.get("legs") or [])
            if len(raw)<2:continue
            weights=[max(0.0,float(x.get("weight",1))) for x in raw];total=sum(weights)
            if total<=0:continue
            legs=[];gross=0.0;ok=True
            for x,w in zip(raw,weights):
                side=str(x.get("side","")).upper();bid=float(x.get("bid") or 0);ask=float(x.get("ask") or 0);symbol=str(x.get("symbol","")).upper().strip()
                if side not in {"LONG","SHORT"} or not symbol or bid<=0 or ask<bid:ok=False;break
                entry=ask if side=="LONG" else bid;budget=self.group_notional*w/total;shares=int(budget/entry)
                if shares<1:ok=False;break
                gross+=shares*entry;legs.append({"symbol":symbol,"side":side,"weight":w,"entry_price":entry,"entry_bid":bid,"entry_ask":ask,"shares":shares})
            if not ok:continue
            signature="+".join(sorted(x["symbol"] for x in legs));gid=f'{d["strategy_id"]}|{signature}|{now.replace(second=0,microsecond=0).isoformat()}'
            if gid in self.seen:continue
            row={"event":"OPEN","group_id":gid,"strategy_id":d["strategy_id"],"opened_at":now.isoformat(),"legs":legs,"gross_notional_used":gross,"target_pct":float(d["target_pct"]),"stop_pct":float(d["stop_pct"]),"max_hold_minutes":int(d["max_hold_minutes"]),"research":d.get("research",{}),"paper_only":True,"broker_execution_enabled":False}
            self.active[gid]=row;self.seen.add(gid);self._append(row);opened+=1
        self._status();return opened
    def update(self,timestamp,quotes):
        now=_dt(timestamp);et=now.astimezone(NY);eod=(et.hour,et.minute)>=(15,55);closing=[]
        for gid,row in list(self.active.items()):
            pnl=0.0;marks=[];complete=True
            for leg in row["legs"]:
                q=quotes.get(leg["symbol"])
                if not q:complete=False;break
                bid=float(q.get("bid") or 0);ask=float(q.get("ask") or 0)
                if bid<=0 or ask<bid:complete=False;break
                exit_price=bid if leg["side"]=="LONG" else ask;sign=1 if leg["side"]=="LONG" else -1;pnl+=sign*(exit_price-leg["entry_price"])*leg["shares"];marks.append({"symbol":leg["symbol"],"side":leg["side"],"exit_price":exit_price,"exit_bid":bid,"exit_ask":ask})
            if not complete:continue
            ret=pnl/row["gross_notional_used"]*100 if row["gross_notional_used"] else 0;held=(now-_dt(row["opened_at"])).total_seconds()/60;reason=None
            if ret>=row["target_pct"]:reason="TARGET"
            elif ret<=-row["stop_pct"]:reason="STOP"
            elif eod:reason="EOD"
            elif held>=row["max_hold_minutes"]:reason="TIMEOUT"
            if reason:closing.append((gid,row,pnl,ret,marks,reason))
        for gid,row,pnl,ret,marks,reason in closing:
            self._append({"event":"CLOSE","group_id":gid,"strategy_id":row["strategy_id"],"opened_at":row["opened_at"],"closed_at":now.isoformat(),"exit_reason":reason,"pnl":pnl,"return_pct_on_gross_notional":ret,"gross_notional_used":row["gross_notional_used"],"exit_legs":marks,"borrow_fees_included":False,"short_locate_verified":False,"paper_only":True,"broker_execution_enabled":False});self.active.pop(gid,None);self.completed+=1
        self._status();return len(closing)
