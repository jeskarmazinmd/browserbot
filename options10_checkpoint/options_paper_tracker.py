"""Conservative debit-only options paper accounting using executable quotes."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os

NY=ZoneInfo("America/New_York")

class OptionsPaperTracker:
    def __init__(self,root="/data"):
        self.root=Path(root);self.ledger=self.root/"options_paper_outcomes.jsonl";self.status=self.root/"options_paper_status.json"
        self.active={};self.seen=set();self.completed=0;self._recover();self._write_status()
    def _recover(self):
        if not self.ledger.exists():return
        with self.ledger.open(errors="replace") as f:
            for line in f:
                try:r=json.loads(line)
                except Exception:continue
                gid=r.get("group_id")
                if not gid:continue
                self.seen.add(gid)
                if r.get("event_type")=="OPTION_ENTRY":self.active[gid]=r
                elif r.get("event_type")=="OPTION_EXIT":self.active.pop(gid,None);self.completed+=1
    def _append(self,row):
        self.root.mkdir(parents=True,exist_ok=True)
        with self.ledger.open("a") as f:f.write(json.dumps(row,separators=(",",":"),default=str)+"\n")
    def _write_status(self):
        self.root.mkdir(parents=True,exist_ok=True);p={"updated_at":datetime.now(timezone.utc).isoformat(),"active":len(self.active),"completed":self.completed,"seen":len(self.seen),"broker_execution_enabled":False,"pricing":"BUY@ask SELL@bid; close BUY@bid SELL@ask"}
        tmp=self.status.with_suffix(".tmp");tmp.write_text(json.dumps(p,separators=(",",":"))+"\n");os.replace(tmp,self.status)
    def register(self,signal):
        gid=f'{signal["strategy_id"]}|{signal["underlying"]}|{signal["timestamp"][:16]}'
        if gid in self.seen:return False
        open_cf=0.0;legs=[]
        for x in signal.get("legs",[]):
            side=x.get("side");mult=int(x.get("multiplier") or 100);bid=float(x.get("bid") or 0);ask=float(x.get("ask") or 0)
            if side=="BUY" and ask>0:price=ask;open_cf-=price*mult
            elif side=="SELL" and bid>0:price=bid;open_cf+=price*mult
            else:return False
            legs.append({**x,"entry_exec":price,"multiplier":mult})
        debit=-open_cf
        # First-generation family deliberately permits debit structures only.
        if debit<=0:return False
        rec={**signal,"event_type":"OPTION_ENTRY","group_id":gid,"legs":legs,"entry_debit":debit,"open_cash_flow":open_cf}
        self.active[gid]=rec;self.seen.add(gid);self._append(rec);self._write_status();return True
    def update(self,snapshot):
        now=snapshot["timestamp"]
        if isinstance(now,str):now=datetime.fromisoformat(now.replace("Z","+00:00"))
        quotes={x["symbol"]:x for x in snapshot.get("contracts",[])}
        for gid,rec in list(self.active.items()):
            if rec.get("underlying")!=snapshot.get("underlying"):continue
            close_cf=0.0;marks=[];complete=True
            for leg in rec["legs"]:
                q=quotes.get(leg["symbol"])
                if not q:complete=False;break
                mult=leg["multiplier"]
                if leg["side"]=="BUY":px=float(q.get("bid") or 0);close_cf+=px*mult
                else:px=float(q.get("ask") or 0);close_cf-=px*mult
                if px<=0:complete=False;break
                marks.append({"symbol":leg["symbol"],"close_exec":px})
            if not complete:continue
            pnl=rec["open_cash_flow"]+close_cf;ret=pnl/rec["entry_debit"]*100
            entered=datetime.fromisoformat(rec["timestamp"].replace("Z","+00:00"));held=(now-entered).total_seconds()/60
            local=now.astimezone(NY);reason=None
            if ret>=float(rec["take_profit_pct"]):reason="TARGET"
            elif ret<=-float(rec["stop_loss_pct"]):reason="STOP"
            elif held>=float(rec["max_hold_minutes"]):reason="TIMEOUT"
            elif (local.hour,local.minute)>=(15,55):reason="EOD"
            if reason:
                row={"event_type":"OPTION_EXIT","group_id":gid,"strategy_id":rec["strategy_id"],"underlying":rec["underlying"],"exit_time":now.isoformat(),"exit_reason":reason,"pnl":pnl,"return_pct":ret,"entry_debit":rec["entry_debit"],"exit_legs":marks}
                self._append(row);self.active.pop(gid);self.completed+=1
        self._write_status()
