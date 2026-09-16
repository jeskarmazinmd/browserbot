"""Self-contained prospective spot-FX experiment: FXUSDB1."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone
import math
import statistics

STRATEGY_ID = 'FXUSDB1'
FAMILY = "FOREX10"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-09T22:00:00+00:00"
MODE = 'BREADTH'
PARAMS = {'lookback': 15, 'move': 0.07, 'tp': 18, 'sl': 14, 'hold': 90}
UNITS_PER_LEG = 10000
MAX_HISTORY = 61


def _ret(history, n):
    if len(history) < n + 1 or history[-n - 1] <= 0:
        return None
    return (history[-1] / history[-n - 1] - 1) * 100


def _leg(q, side):
    return {
        "symbol": q["symbol"], "side": side,
        "bid": float(q["bid"]), "ask": float(q["ask"]),
        "units": UNITS_PER_LEG,
    }


class Strategy:
    name = STRATEGY_ID

    def __init__(self):
        self._h = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
        self._last = None

    def _push(self, symbol, q):
        self._h[symbol].append((float(q["bid"]) + float(q["ask"])) / 2)

    def evaluate(self, snapshot):
        now = snapshot["timestamp"]
        if isinstance(now, str):
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))
        now = now.astimezone(timezone.utc)
        if now < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        quotes = snapshot.get("pairs", {})
        for symbol, q in quotes.items():
            if q.get("realtime") is True and float(q.get("bid") or 0) > 0 and float(q.get("ask") or 0) >= float(q.get("bid") or 0):
                self._push(symbol, q)
        if self._last and (now - self._last).total_seconds() < 20 * 60:
            return []

        legs = None
        research = {"mode": MODE}

        if MODE in {"TREND", "REV", "BREAK", "SESSION"}:
            pair = PARAMS["pair"]
            q = quotes.get(pair)
            h = list(self._h[pair])
            n = int(PARAMS["lookback"])
            if not q:
                return []
            if MODE == "SESSION" and not (PARAMS["start_hour_utc"] <= now.hour < PARAMS["end_hour_utc"]):
                return []
            r = _ret(h, n)
            if r is None:
                return []
            if MODE in {"TREND", "SESSION"} and abs(r) >= PARAMS["move"]:
                legs = [_leg(q, "LONG" if r > 0 else "SHORT")]
                research["return_pct"] = r
            elif MODE == "REV":
                one = _ret(h, 1)
                if one is not None and abs(r) >= PARAMS["move"] and r * one < 0 and abs(one) >= PARAMS["rebound"]:
                    legs = [_leg(q, "LONG" if r < 0 else "SHORT")]
                    research.update({"prior_return_pct": r, "rebound_pct": one})
            elif MODE == "BREAK" and len(h) >= n + 1:
                prior = h[-n-1:-1]
                upper = max(prior) * (1 + PARAMS["buffer"] / 100)
                lower = min(prior) * (1 - PARAMS["buffer"] / 100)
                if h[-1] > upper:
                    legs = [_leg(q, "LONG")]
                elif h[-1] < lower:
                    legs = [_leg(q, "SHORT")]
                research.update({"upper": upper, "lower": lower})

        elif MODE == "PAIR":
            a, b = PARAMS["a"], PARAMS["b"]
            qa, qb = quotes.get(a), quotes.get(b)
            ha, hb = list(self._h[a]), list(self._h[b])
            n = int(PARAMS["lookback"])
            if not qa or not qb or len(ha) < n + 1 or len(hb) < n + 1:
                return []
            ratios = [math.log(x / y) for x, y in zip(ha[-n-1:], hb[-n-1:]) if x > 0 and y > 0]
            if len(ratios) != n + 1:
                return []
            sd = statistics.pstdev(ratios[:-1])
            z = (ratios[-1] - statistics.mean(ratios[:-1])) / sd if sd > 0 else 0
            if abs(z) >= PARAMS["z"]:
                # Mean-reversion pair: short the relatively rich leg, long the cheap leg.
                legs = [_leg(qa, "SHORT" if z > 0 else "LONG"), _leg(qb, "LONG" if z > 0 else "SHORT")]
                research["ratio_z"] = z

        elif MODE == "BREADTH":
            usd_base = ("USD/JPY", "USD/CAD", "USD/CHF")
            usd_quote = ("EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD")
            values = []
            for pair in usd_base:
                r = _ret(list(self._h[pair]), PARAMS["lookback"])
                if r is not None:
                    values.append(r)
            for pair in usd_quote:
                r = _ret(list(self._h[pair]), PARAMS["lookback"])
                if r is not None:
                    values.append(-r)
            eur = quotes.get("EUR/USD")
            if eur and len(values) >= 5:
                strength = statistics.mean(values)
                if abs(strength) >= PARAMS["move"]:
                    legs = [_leg(eur, "SHORT" if strength > 0 else "LONG")]
                    research["usd_breadth_pct"] = strength

        if not legs:
            return []
        self._last = now
        return [{
            "strategy_id": STRATEGY_ID, "timestamp": now.isoformat(), "legs": legs,
            "take_profit_dollars": PARAMS["tp"], "stop_loss_dollars": PARAMS["sl"],
            "max_hold_minutes": PARAMS["hold"], "paper_only": True,
            "live_order_placement": False, "research": research,
        }]
