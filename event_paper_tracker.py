from __future__ import annotations

import json,os
from datetime import datetime,timezone
from pathlib import Path

from executable_paper_engine import EXECUTION_MODEL,classify_limit_order,executable_mark


class EventPaperTracker:
    LEDGER_NAME="event_paper_v2_bidask_outcomes.jsonl"
    STATUS_NAME="event_paper_v2_bidask_status.json"

    def __init__(self,root,notional_per_signal=1000.0):
        self.root=Path(root)
        self.ledger=self.root/self.LEDGER_NAME
        self.status_path=self.root/self.STATUS_NAME
        self.notional_per_signal=float(notional_per_signal)
        self.active={}
        self.seen=set()
        self.completed=0
        self._restore()
        self._save()

    def _key(self,d):
        return f'{d["strategy_id"]}:{d["event_id"]}'

    def _append(self,row):
        self.root.mkdir(parents=True,exist_ok=True)
        with self.ledger.open("a") as f:
            f.write(json.dumps(row,separators=(",",":"),default=str)+"\n")

    def _restore(self):
        if not self.ledger.exists():
            return
        try:
            lines=self.ledger.read_text().splitlines()
        except Exception:
            return
        for line in lines:
            try:
                row=json.loads(line)
                key=row.get("key")
                event=row.get("event")
                if not key:
                    continue
                if event=="OPEN_ATTEMPT":
                    self.seen.add(key)
                elif event=="OPEN":
                    self.seen.add(key)
                    self.active[key]=row
                elif event=="CLOSE":
                    if row.get("position_closed",True):
                        self.active.pop(key,None)
                    else:
                        current=self.active.get(key)
                        if current:
                            current["shares"]=int(row["remaining_shares"])
                    self.completed+=int(bool(row.get("position_closed",True)))
            except Exception:
                continue

    def register(self,d,quote):
        key=self._key(d)
        if key in self.seen:
            return False

        self.seen.add(key)
        d=dict(d)
        side=str(d.get("side","")).upper()
        symbol=str(d.get("symbol","")).upper().strip()
        action="BUY" if side=="LONG" else "SELL"

        signal_bid=d.get("entry_bid")
        signal_ask=d.get("entry_ask")
        model_entry=signal_ask if action=="BUY" else signal_bid

        try:
            model_entry=float(model_entry)
            requested=max(1,int(self.notional_per_signal/model_entry))
        except (TypeError,ValueError,ZeroDivisionError):
            execution={
                "execution_model":EXECUTION_MODEL,
                "outcome":"UNKNOWN",
                "reason":"INVALID_SIGNAL_REFERENCE_PRICE",
                "action":action,
                "price_source":"ASK" if action=="BUY" else "BID",
                "requested_qty":0,
                "filled_qty":0,
            }
            self._append({
                **d,"key":key,"event":"OPEN_ATTEMPT",
                "signal_bid":signal_bid,"signal_ask":signal_ask,
                "execution":execution,
            })
            self._save()
            return False

        if not quote:
            execution={
                "execution_model":EXECUTION_MODEL,
                "outcome":"UNKNOWN",
                "reason":"MISSING_EXECUTION_QUOTE",
                "action":action,
                "price_source":"ASK" if action=="BUY" else "BID",
                "requested_qty":requested,
                "filled_qty":0,
            }
        else:
            execution=classify_limit_order(
                quote,
                action=action,
                limit_price=model_entry,
                requested_qty=requested,
            ).as_dict()

        if execution["outcome"] not in ("FULL","PARTIAL"):
            self._append({
                **d,"key":key,"event":"OPEN_ATTEMPT",
                "signal_bid":signal_bid,"signal_ask":signal_ask,
                "requested_shares":requested,
                "execution":execution,
            })
            self._save()
            return False

        filled=int(execution["filled_qty"])
        row={
            **d,
            "key":key,
            "event":"OPEN",
            "signal_bid":signal_bid,
            "signal_ask":signal_ask,
            "entry_price":float(execution["fill_price"]),
            "requested_shares":requested,
            "shares":filled,
            "opened_at":d.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "execution_model":EXECUTION_MODEL,
            "execution":execution,
        }
        self.active[key]=row
        self._append(row)
        self._save()
        return True

    def update(self,now,quotes):
        closed=0
        for key,d in list(self.active.items()):
            q=quotes.get(d["symbol"])
            side=d["side"]
            action="SELL" if side=="LONG" else "BUY"

            mark=executable_mark(q,action=action,now=now) if q else {
                "state":"UNKNOWN",
                "reason":"MISSING_EXECUTION_QUOTE",
                "price":None,
                "price_source":"BID" if action=="SELL" else "ASK",
                "execution_model":EXECUTION_MODEL,
            }

            if mark.get("state")!="EXECUTABLE":
                continue

            mark_price=float(mark["price"])
            entry=float(d["entry_price"])
            ret=(mark_price/entry-1)*(1 if side=="LONG" else -1)
            age=(now-datetime.fromisoformat(d["opened_at"])).total_seconds()/60

            reason=(
                "TARGET" if ret>=float(d["target_fraction"])
                else "STOP" if ret<=-float(d["stop_fraction"])
                else "TIME" if age>=int(d["hold_minutes"])
                else None
            )
            if not reason:
                continue

            execution=classify_limit_order(
                q,
                action=action,
                limit_price=mark_price,
                requested_qty=int(d["shares"]),
                now=now,
            ).as_dict()

            if execution["outcome"] not in ("FULL","PARTIAL"):
                self._append({
                    "key":key,
                    "strategy_id":d["strategy_id"],
                    "event_id":d["event_id"],
                    "symbol":d["symbol"],
                    "side":side,
                    "event":"CLOSE_ATTEMPT",
                    "exit_reason":reason,
                    "execution":execution,
                    "timestamp":now.isoformat(),
                })
                continue

            qty=int(execution["filled_qty"])
            exit_price=float(execution["fill_price"])
            pnl_per_share=(exit_price-entry)*(1 if side=="LONG" else -1)
            remaining=int(d["shares"])-qty
            position_closed=remaining==0

            row={
                "key":key,
                "strategy_id":d["strategy_id"],
                "event_id":d["event_id"],
                "symbol":d["symbol"],
                "side":side,
                "event":"CLOSE",
                "opened_at":d["opened_at"],
                "closed_at":now.isoformat(),
                "entry_price":entry,
                "exit_price":exit_price,
                "shares":qty,
                "remaining_shares":remaining,
                "position_closed":position_closed,
                "return_fraction":(exit_price/entry-1)*(1 if side=="LONG" else -1),
                "pnl":pnl_per_share*qty,
                "exit_reason":reason,
                "execution_model":EXECUTION_MODEL,
                "execution":execution,
            }
            self._append(row)

            if position_closed:
                self.active.pop(key,None)
                self.completed+=1
                closed+=1
            else:
                d["shares"]=remaining

        self._save()
        return closed

    def _save(self):
        self.root.mkdir(parents=True,exist_ok=True)
        tmp=self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "updated_at":datetime.now(timezone.utc).isoformat(),
            "active":len(self.active),
            "completed":self.completed,
            "seen":len(self.seen),
            "notional_per_signal":self.notional_per_signal,
            "execution_model":EXECUTION_MODEL,
            "broker_execution_enabled":False,
            "bid_ask_spread_included":True,
            "quote_freshness_enforced":True,
            "liquidity_checked":True,
            "pricing":"BIDASK_EXEC_V1; LONG BUY@ask SELL@bid; SHORT SELL@bid BUY@ask; displayed top-of-book liquidity",
            "event_timestamp_causality_enforced":True,
        },separators=(",",":"))+"\n")
        os.replace(tmp,self.status_path)
