from __future__ import annotations
import json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
class EventPaperTracker:
    def __init__(self,root):
        self.root=Path(root);self.active={};self.seen=set();self.completed=0;self._save()
    def register(self,d):
        key=f'{d["strategy_id"]}:{d["event_id"]}'
        if key in self.seen:return False
        self.seen.add(key);side=d["side"];d=dict(d);d["entry_price"]=float(d["entry_ask"] if side=="LONG" else d["entry_bid"]);d["opened_at"]=datetime.now(timezone.utc).isoformat();self.active[key]=d;self._save();return True
    def update(self,now,quotes):
        done=[]
        for key,d in self.active.items():
            q=quotes.get(d["symbol"])
            if not q:continue
            side=d["side"];exit_price=float(q["bid"] if side=="LONG" else q["ask"]);entry=float(d["entry_price"]);ret=(exit_price/entry-1)*(1 if side=="LONG" else -1)
            age=(now-datetime.fromisoformat(d["opened_at"])).total_seconds()/60
            reason="TARGET" if ret>=float(d["target_fraction"]) else "STOP" if ret<=-float(d["stop_fraction"]) else "TIME" if age>=int(d["hold_minutes"]) else None
            if reason:
                row={**d,"closed_at":now.isoformat(),"exit_price":exit_price,"return_fraction":ret,"exit_reason":reason}
                with (self.root/"event_paper_outcomes.jsonl").open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
                done.append(key);self.completed+=1
        for key in done:self.active.pop(key,None)
        self._save()
    def _save(self):
        self.root.mkdir(parents=True,exist_ok=True);p=self.root/"event_paper_status.json";tmp=p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),"active":len(self.active),"completed_this_process":self.completed,"seen":len(self.seen),"notional_per_signal":1000.0,"broker_execution_enabled":False,"pricing":"LONG open@ask close@bid; SHORT open@bid close@ask; whole shares","event_timestamp_causality_enforced":True},separators=(",",":"))+"\n");os.replace(tmp,p)
