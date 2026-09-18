"""Atomic executable bid/ask shadow for generic coordinated trades."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import math

from executable_paper_engine import (
    EXECUTION_MODEL,
    classify_limit_order,
    executable_mark,
)
from multi_leg_paper_tracker import MultiLegPaperTracker, _utc


FILE_STEM = "multi_leg_paper_v2_bidask"
INDEPENDENT_FILE_STEM = "multi_leg_paper_v3_bidask_independent"
MAX_PENDING_SECONDS = 20.0
MAX_SYMBOLS_PER_CYCLE = 50
MAX_LEG_QUOTE_SKEW_MS = 5000.0


def _positive(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


class BidAskMultiLegPaperTracker(MultiLegPaperTracker):
    """Require every coordinated leg to receive a full executable fill."""

    def __init__(self, data_root, **kwargs):
        kwargs.setdefault("file_stem", FILE_STEM)
        kwargs.setdefault("require_complete_exit", True)
        super().__init__(data_root, **kwargs)
        self.pending = OrderedDict()
        self.entry_full_groups = 0
        self.entry_rejected_groups = 0
        self._write_status()

    def _write_status(self):
        self._atomic_json(
            self.status_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active_groups": len(self.active),
                "pending_groups": len(getattr(self, "pending", {})),
                "completed_groups": self.completed,
                "seen_groups": len(self.seen),
                "group_notional": self.group_notional,
                "execution_model": EXECUTION_MODEL,
                "pricing": "LONG BUY@ask SELL@bid; SHORT SELL@bid BUY@ask",
                "atomic_full_group_entry": True,
                "fresh_complete_group_exit": True,
                "displayed_liquidity_enforced": True,
                "broker_execution_enabled": False,
                "entry_full_groups": getattr(self, "entry_full_groups", 0),
                "entry_rejected_groups": getattr(self, "entry_rejected_groups", 0),
                "max_symbols_per_cycle": MAX_SYMBOLS_PER_CYCLE,
            },
        )

    def register(self, signal):
        try:
            timestamp = _utc(signal.get("timestamp"))
        except (TypeError, ValueError):
            return False
        strategy_id = str(signal.get("strategy_id") or "").strip()
        legs = signal.get("legs")
        if not strategy_id or not isinstance(legs, list) or len(legs) < 2:
            return False
        group_id = self._group_id(signal, timestamp)
        if group_id in self.seen or group_id in self.pending:
            return False
        symbols = set()
        for leg in legs:
            symbol = str((leg or {}).get("symbol") or "").upper().strip()
            side = str((leg or {}).get("side") or "").upper().strip()
            if (
                not symbol
                or symbol in symbols
                or side not in {"LONG", "SHORT"}
                or _positive((leg or {}).get("entry_price")) is None
                or _positive((leg or {}).get("weight")) is None
            ):
                return False
            symbols.add(symbol)
        queued = dict(signal)
        queued["group_id"] = group_id
        queued["bidask_queued_at"] = datetime.now(timezone.utc).isoformat()
        self.pending[group_id] = queued
        self._write_status()
        return True

    def symbols(self, limit=MAX_SYMBOLS_PER_CYCLE):
        symbols = []
        for signal in self.pending.values():
            symbols.extend(str(leg.get("symbol") or "").upper() for leg in signal["legs"])
        for record in self.active.values():
            symbols.extend(str(leg.get("symbol") or "").upper() for leg in record["legs"])
        return set(list(dict.fromkeys(filter(None, symbols)))[: int(limit)])

    def _reject(self, group_id, signal, now, reason, decisions=None):
        self._append({
            "event_type": "MULTI_LEG_ENTRY_REJECTED",
            "group_id": group_id,
            "strategy_id": signal.get("strategy_id"),
            "signal_timestamp": signal.get("timestamp"),
            "recorded_at": now.isoformat(),
            "reason": reason,
            "leg_executions": decisions or [],
            "execution_model": EXECUTION_MODEL,
            "paper_only": True,
            "broker_execution_enabled": False,
        })
        self.seen.add(group_id)
        self.pending.pop(group_id, None)
        self.entry_rejected_groups += 1

    def update_quotes(self, quotes, now):
        now = _utc(now)
        for group_id, signal in list(self.pending.items()):
            age = (now - _utc(signal["bidask_queued_at"])).total_seconds()
            total_weight = sum(float(leg["weight"]) for leg in signal["legs"])
            transformed = []
            decisions = []
            controlling_times = []
            waiting = False
            rejection = None
            for leg in signal["legs"]:
                symbol = str(leg["symbol"]).upper()
                side = str(leg["side"]).upper()
                quote = quotes.get(symbol)
                if quote is None:
                    waiting = True
                    continue
                action = "BUY" if side == "LONG" else "SELL"
                executable_price = _positive(
                    quote.get("ask" if action == "BUY" else "bid")
                )
                if executable_price is None:
                    waiting = True
                    continue
                budget = self.group_notional * float(leg["weight"]) / total_weight
                requested = max(1, int(budget / executable_price))
                decision = classify_limit_order(
                    quote,
                    action=action,
                    limit_price=executable_price,
                    requested_qty=requested,
                    now=now,
                    max_quote_age_ms=5000.0,
                )
                decisions.append({"symbol": symbol, **decision.as_dict()})
                if decision.outcome != "FULL":
                    if decision.outcome in {"ZERO", "PARTIAL"}:
                        rejection = f"{symbol}:{decision.outcome}:{decision.reason}"
                    else:
                        waiting = True
                    continue
                time_key = "ask_time_ms" if action == "BUY" else "bid_time_ms"
                if quote.get(time_key) is not None:
                    controlling_times.append(float(quote[time_key]))
                transformed.append({
                    **leg,
                    "symbol": symbol,
                    "side": side,
                    "entry_price": float(decision.fill_price),
                    "entry_bid": decision.bid,
                    "entry_ask": decision.ask,
                    "requested_qty": decision.requested_qty,
                    "filled_qty": decision.filled_qty,
                    "entry_quote_age_ms": decision.quote_age_ms,
                    "displayed_qty": decision.displayed_qty,
                    "execution_model": EXECUTION_MODEL,
                })

            if rejection is None and len(controlling_times) >= 2:
                if max(controlling_times) - min(controlling_times) > MAX_LEG_QUOTE_SKEW_MS:
                    rejection = "leg_quote_times_not_simultaneous"
            if rejection is not None:
                self._reject(group_id, signal, now, rejection, decisions)
                continue
            if waiting or len(transformed) != len(signal["legs"]):
                if age > MAX_PENDING_SECONDS:
                    self._reject(group_id, signal, now, "entry_evidence_timeout", decisions)
                continue

            accepted = super().register({
                **signal,
                "legs": transformed,
                "execution_model": EXECUTION_MODEL,
                "pricing": "LONG BUY@ask SELL@bid; SHORT SELL@bid BUY@ask",
            })
            self.pending.pop(group_id, None)
            if accepted:
                self.entry_full_groups += 1

        prices = {}
        for record in self.active.values():
            for leg in record["legs"]:
                symbol = str(leg["symbol"]).upper()
                quote = quotes.get(symbol)
                action = "SELL" if leg["side"] == "LONG" else "BUY"
                mark = executable_mark(
                    quote,
                    action=action,
                    now=now,
                    max_quote_age_ms=5000.0,
                )
                if mark.get("state") == "EXECUTABLE":
                    prices[symbol] = mark["price"]
        closed = super().update(prices, now)
        self._write_status()
        return closed


class IndependentBidAskMultiLegTracker(BidAskMultiLegPaperTracker):
    """Accept raw coordinated signals without a LAST group admission gate."""

    def __init__(self, data_root, **kwargs):
        kwargs.setdefault("file_stem", INDEPENDENT_FILE_STEM)
        super().__init__(data_root, **kwargs)

    def register_signal(self, signal, quotes, now):
        if not self.register(signal):
            return False
        group_id = self._group_id(signal, _utc(signal["timestamp"]))
        now = _utc(now)
        self.update_quotes(quotes, now)
        pending = self.pending.get(group_id)
        if pending is not None:
            self._reject(group_id, pending, now, "signal_cycle_quote_unavailable")
            self._write_status()
        return group_id in self.active
