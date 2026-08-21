"""Independent bid/ask paper accounting for cross-sectional research."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def _dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _atomic(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n"); tmp.replace(path)


class CrossSectionPaperTracker:
    def __init__(self, root="/data", notional=1000.0):
        self.root=Path(root); self.notional=float(notional)
        self.ledger=self.root/"crosssection_paper_outcomes.jsonl"; self.status_path=self.root/"crosssection_paper_status.json"
        self.active={}; self.seen=set(); self.completed=0; self._restore(); self._status()

    def _restore(self):
        if not self.ledger.exists(): return
        try:
            for line in self.ledger.read_text(errors="replace").splitlines():
                try: row=json.loads(line)
                except Exception: continue
                key=row.get("setup_id")
                if not key: continue
                self.seen.add(key)
                if row.get("event")=="OPEN": self.active[key]=row
                elif row.get("event")=="CLOSE": self.active.pop(key,None); self.completed+=1
        except OSError: pass

    def _append(self,row):
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        with self.ledger.open("a") as f: f.write(json.dumps(row,separators=(",",":"))+"\n")

    def _status(self):
        _atomic(self.status_path,{"updated_at":datetime.now(timezone.utc).isoformat(),"active":len(self.active),"completed":self.completed,"seen":len(self.seen),"notional_per_leg":self.notional,"broker_execution_enabled":False,"bid_ask_spread_included":True,"pricing":"LONG open@ask close@bid; SHORT open@bid close@ask; whole shares"})

    def open_decisions(self,decisions):
        opened=0
        for d in decisions:
            side=str(d.get("side","")).upper()
            if side not in {"LONG","SHORT"}: continue
            now=_dt(d["timestamp"]); symbol=str(d.get("symbol","")).upper().strip(); bid=float(d.get("bid") or 0); ask=float(d.get("ask") or 0)
            if not symbol or bid<=0 or ask<bid: continue
            entry=ask if side=="LONG" else bid; shares=int(self.notional/entry)
            if shares<1: continue
            key=f'{d["strategy_id"]}|{symbol}|{now.replace(second=0,microsecond=0).isoformat()}'
            if key in self.seen: continue
            tp=float(d["target_pct"]); sp=float(d["stop_pct"])
            target=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); stop=entry*(1-sp/100) if side=="LONG" else entry*(1+sp/100)
            row={"event":"OPEN","setup_id":key,"strategy_id":d["strategy_id"],"symbol":symbol,"side":side,"opened_at":now.isoformat(),"entry_price":entry,"entry_bid":bid,"entry_ask":ask,"shares":shares,"notional_used":shares*entry,"target_price":target,"stop_price":stop,"max_hold_minutes":int(d["max_hold_minutes"]),"research":d.get("research",{}),"paper_only":True,"broker_execution_enabled":False}
            self.active[key]=row; self.seen.add(key); self._append(row); opened+=1
        self._status(); return opened

    def update(self,timestamp,quotes):
        now=_dt(timestamp); et=now.astimezone(NY); eod=(et.hour,et.minute)>=(15,55); closed=[]
        for key,row in list(self.active.items()):
            q=quotes.get(row["symbol"])
            if not q: continue
            bid=float(q.get("bid") or 0); ask=float(q.get("ask") or 0)
            if bid<=0 or ask<bid: continue
            exit_price=bid if row["side"]=="LONG" else ask; held=(now-_dt(row["opened_at"])).total_seconds()/60; reason=None
            if row["side"]=="LONG":
                if exit_price>=row["target_price"]: reason="TARGET"
                elif exit_price<=row["stop_price"]: reason="STOP"
            else:
                if exit_price<=row["target_price"]: reason="TARGET"
                elif exit_price>=row["stop_price"]: reason="STOP"
            if reason is None and eod: reason="EOD"
            if reason is None and held>=row["max_hold_minutes"]: reason="TIMEOUT"
            if reason: closed.append((key,row,exit_price,bid,ask,reason))
        for key,row,exit_price,bid,ask,reason in closed:
            sign=1 if row["side"]=="LONG" else -1; pnl=sign*(exit_price-row["entry_price"])*row["shares"]; ret=sign*(exit_price-row["entry_price"])/row["entry_price"]*100
            self._append({"event":"CLOSE","setup_id":key,"strategy_id":row["strategy_id"],"symbol":row["symbol"],"side":row["side"],"opened_at":row["opened_at"],"closed_at":now.isoformat(),"entry_price":row["entry_price"],"exit_price":exit_price,"exit_bid":bid,"exit_ask":ask,"shares":row["shares"],"exit_reason":reason,"return_pct":ret,"pnl":pnl,"paper_only":True,"broker_execution_enabled":False})
            self.active.pop(key,None); self.completed+=1
        self._status(); return len(closed)
