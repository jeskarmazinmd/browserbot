"""Independent prospective Q-like reversal + TD1-like strength experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import math
import statistics
from zoneinfo import ZoneInfo

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "QTD1X"
FAMILY = "ORTHO"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"


def _return_pct(old: float, new: float) -> float:
    return (new / old - 1.0) * 100.0 if old > 0 else math.nan


def _at_or_before(history, when):
    answer = None
    for ts, price, volume in history:
        if ts <= when:
            answer = (ts, price, volume)
        else:
            break
    return answer


def _minute_prices(history, timestamp, minutes):
    values = []
    for ago in range(minutes, -1, -1):
        item = _at_or_before(history, timestamp - timedelta(minutes=ago))
        if item is None:
            return None
        values.append(float(item[1]))
    return values


def _q_candidate(history, timestamp):
    prices = _minute_prices(history, timestamp, 33)
    if prices is None:
        return None
    pre = prices[:-3]
    returns = [_return_pct(a, b) for a, b in zip(pre, pre[1:])]
    if not returns or any(math.isnan(x) for x in returns):
        return None
    pre_std = statistics.pstdev(returns)
    flash = prices[-4:]
    flash_start = flash[0]
    low = min(flash)
    current = flash[-1]
    drop = (flash_start - low) / flash_start * 100.0 if flash_start > 0 else 0.0
    rebound = _return_pct(low, current)
    units = drop / pre_std if pre_std > 0 else 0.0
    if drop < 1.0 or rebound < 0.10 or units < 3.0:
        return None
    target = low + 0.60 * (flash_start - low)
    if target <= current:
        return None
    return {
        "entry_price": current,
        "target_price": target,
        "stop_price": current * 0.95,
        "flash_drop_pct": drop,
        "rebound_pct": rebound,
        "pre30_return_std_pct": pre_std,
        "flash_drop_volatility_units": units,
    }


def _td_candidate(stock_history, spy_history, timestamp):
    stock = _minute_prices(stock_history, timestamp, 30)
    spy = _minute_prices(spy_history, timestamp, 30)
    if stock is None or spy is None:
        return None
    ret30 = _return_pct(stock[0], stock[-1])
    ret5 = _return_pct(stock[-6], stock[-1])
    spy30 = _return_pct(spy[0], spy[-1])
    excess = ret30 - spy30
    if ret30 < 0.60 or excess < 0.50 or ret5 <= 0:
        return None
    price = stock[-1]
    return {
        "entry_price": price,
        "target_price": price * 1.0075,
        "stop_price": price * 0.9945,
        "return_30m_pct": ret30,
        "return_5m_pct": ret5,
        "spy_return_30m_pct": spy30,
        "excess_return_30m_pct": excess,
    }


def _event(snapshot, symbol, mode, candidate):
    return SignalEvent(
        timestamp=snapshot.timestamp,
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        signal_type="SIGNAL",
        data={
            **candidate,
            "setup": f"orthogonal_{mode.lower()}",
            "orthogonal_mode": mode,
            "paper_only": True,
            "live_order_placement": False,
            "forward_start_utc": FORWARD_START_UTC,
        },
    )


class QTD1XStrategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=45))

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol, quote in snapshot.quotes.items():
            self._history[symbol].append(
                (snapshot.timestamp, float(quote.price), quote.total_volume)
            )

        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []

        spy = self._history.get("SPY")
        et = snapshot.timestamp.astimezone(ZoneInfo("America/New_York"))
        minute_et = et.hour * 60 + et.minute
        out = []

        for symbol in snapshot.quotes:
            if symbol == "SPY":
                continue
            q = _q_candidate(self._history[symbol], snapshot.timestamp)
            td = None
            if spy is not None and 10 * 60 <= minute_et <= 11 * 60 + 30:
                td = _td_candidate(self._history[symbol], spy, snapshot.timestamp)
            if q is not None and td is not None:
                merged = dict(q)
                merged.update({f"td_{k}": v for k, v in td.items() if k not in {"entry_price", "target_price", "stop_price"}})
                out.append(_event(snapshot, symbol, "Q_AND_TD1", merged))
            elif q is not None:
                out.append(_event(snapshot, symbol, "Q", q))
            elif td is not None:
                out.append(_event(snapshot, symbol, "TD1", td))
        return out


def metadata():
    return {
        "strategy_id": STRATEGY_ID,
        "family": FAMILY,
        "paper_only": PAPER_ONLY,
        "forward_start_utc": FORWARD_START_UTC,
        "design": "self_contained_two_mode",
    }
