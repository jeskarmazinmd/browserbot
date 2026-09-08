"""Independent bid/ask paper accounting for cross-sectional research."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from executable_paper_engine import EXECUTION_MODEL, classify_limit_order, executable_mark

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
        self.ledger=self.root/"crosssection_paper_v2_bidask_outcomes.jsonl"; self.status_path=self.root/"crosssection_paper_v2_bidask_status.json"
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
                if row.get("event")=="OPEN":
                    self.active[key]=row
                elif row.get("event")=="CLOSE":
                    if row.get("position_closed", True):
                        self.active.pop(key,None)
                        self.completed+=1
                    elif key in self.active:
                        self.active[key]["shares"]=int(row.get("remaining_shares") or 0)
        except OSError: pass

    def _append(self,row):
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        with self.ledger.open("a") as f: f.write(json.dumps(row,separators=(",",":"))+"\n")

    def _status(self):
        _atomic(self.status_path,{
            "updated_at":datetime.now(timezone.utc).isoformat(),
            "active":len(self.active),
            "completed":self.completed,
            "seen":len(self.seen),
            "notional_per_leg":self.notional,
            "execution_model":EXECUTION_MODEL,
            "broker_execution_enabled":False,
            "bid_ask_spread_included":True,
            "quote_freshness_enforced":True,
            "liquidity_checked":True,
            "pricing":"BIDASK_EXEC_V1; LONG BUY@ask SELL@bid; SHORT SELL@bid BUY@ask; displayed top-of-book liquidity",
        })

    def open_decisions(self,decisions):
        opened=0
        for d in decisions:
            side=str(d.get("side","")).upper()
            if side not in {"LONG","SHORT"}: continue
            now=_dt(d["timestamp"])
            symbol=str(d.get("symbol","")).upper().strip()
            if not symbol: continue

            try:
                bid=float(d.get("bid") or 0)
                ask=float(d.get("ask") or 0)
            except (TypeError,ValueError):
                continue
            if bid<=0 or ask<bid: continue

            model_entry=ask if side=="LONG" else bid
            requested_shares=int(self.notional/model_entry)
            if requested_shares<1: continue

            key=f'{d["strategy_id"]}|{symbol}|{now.replace(second=0,microsecond=0).isoformat()}'
            if key in self.seen: continue

            action="BUY" if side=="LONG" else "SELL"
            execution=classify_limit_order(
                d,
                action=action,
                limit_price=model_entry,
                requested_qty=requested_shares,
                now=now,
            )

            self.seen.add(key)

            if execution.outcome not in {"FULL","PARTIAL"} or not execution.filled_qty or execution.fill_price is None:
                self._append({
                    "event":"OPEN_ATTEMPT",
                    "setup_id":key,
                    "strategy_id":d["strategy_id"],
                    "symbol":symbol,
                    "side":side,
                    "opened_at":now.isoformat(),
                    "requested_shares":requested_shares,
                    "filled_shares":int(execution.filled_qty or 0),
                    "execution":execution.as_dict(),
                    "execution_model":EXECUTION_MODEL,
                    "paper_only":True,
                    "broker_execution_enabled":False,
                })
                continue

            entry=float(execution.fill_price)
            shares=int(execution.filled_qty)
            tp=float(d["target_pct"]); sp=float(d["stop_pct"])
            target=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100)
            stop=entry*(1-sp/100) if side=="LONG" else entry*(1+sp/100)

            row={
                "event":"OPEN",
                "setup_id":key,
                "strategy_id":d["strategy_id"],
                "symbol":symbol,
                "side":side,
                "opened_at":now.isoformat(),
                "entry_price":entry,
                "entry_bid":execution.bid,
                "entry_ask":execution.ask,
                "requested_shares":requested_shares,
                "shares":shares,
                "notional_used":shares*entry,
                "target_price":target,
                "stop_price":stop,
                "max_hold_minutes":int(d["max_hold_minutes"]),
                "research":d.get("research",{}),
                "execution":execution.as_dict(),
                "execution_model":EXECUTION_MODEL,
                "paper_only":True,
                "broker_execution_enabled":False,
            }
            self.active[key]=row
            self._append(row)
            opened+=1

        self._status()
        return opened

    def update(self,timestamp,quotes):
        now=_dt(timestamp)
        et=now.astimezone(NY)
        eod=(et.hour,et.minute)>=(15,55)
        fills=0

        for key,row in list(self.active.items()):
            q=quotes.get(row["symbol"])
            if not q: continue

            action="SELL" if row["side"]=="LONG" else "BUY"
            mark=executable_mark(q,action=action,now=now)
            if mark["state"]!="EXECUTABLE":
                continue

            exit_price=float(mark["price"])
            held=(now-_dt(row["opened_at"])).total_seconds()/60
            reason=None

            if row["side"]=="LONG":
                if exit_price>=row["target_price"]: reason="TARGET"
                elif exit_price<=row["stop_price"]: reason="STOP"
            else:
                if exit_price<=row["target_price"]: reason="TARGET"
                elif exit_price>=row["stop_price"]: reason="STOP"

            if reason is None and eod: reason="EOD"
            if reason is None and held>=row["max_hold_minutes"]: reason="TIMEOUT"
            if reason is None: continue

            requested_shares=int(row["shares"])
            execution=classify_limit_order(
                q,
                action=action,
                limit_price=exit_price,
                requested_qty=requested_shares,
                now=now,
            )

            if execution.outcome not in {"FULL","PARTIAL"} or not execution.filled_qty or execution.fill_price is None:
                self._append({
                    "event":"CLOSE_ATTEMPT",
                    "setup_id":key,
                    "strategy_id":row["strategy_id"],
                    "symbol":row["symbol"],
                    "side":row["side"],
                    "opened_at":row["opened_at"],
                    "attempted_at":now.isoformat(),
                    "exit_reason":reason,
                    "requested_shares":requested_shares,
                    "filled_shares":int(execution.filled_qty or 0),
                    "execution":execution.as_dict(),
                    "execution_model":EXECUTION_MODEL,
                    "paper_only":True,
                    "broker_execution_enabled":False,
                })
                continue

            filled_shares=int(execution.filled_qty)
            actual_exit=float(execution.fill_price)
            remaining=max(0,requested_shares-filled_shares)
            sign=1 if row["side"]=="LONG" else -1
            pnl=sign*(actual_exit-row["entry_price"])*filled_shares
            ret=sign*(actual_exit-row["entry_price"])/row["entry_price"]*100
            position_closed=remaining==0

            self._append({
                "event":"CLOSE",
                "setup_id":key,
                "strategy_id":row["strategy_id"],
                "symbol":row["symbol"],
                "side":row["side"],
                "opened_at":row["opened_at"],
                "closed_at":now.isoformat(),
                "entry_price":row["entry_price"],
                "exit_price":actual_exit,
                "exit_bid":execution.bid,
                "exit_ask":execution.ask,
                "requested_shares":requested_shares,
                "shares":filled_shares,
                "remaining_shares":remaining,
                "position_closed":position_closed,
                "exit_reason":reason,
                "return_pct":ret,
                "pnl":pnl,
                "execution":execution.as_dict(),
                "execution_model":EXECUTION_MODEL,
                "paper_only":True,
                "broker_execution_enabled":False,
            })

            fills+=1
            if position_closed:
                self.active.pop(key,None)
                self.completed+=1
            else:
                row["shares"]=remaining

        self._status()
        return fills
