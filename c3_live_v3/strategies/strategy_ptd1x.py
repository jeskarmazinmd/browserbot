"""Independent prospective P-like pretrend reversal + TD1-like strength experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "PTD1X"
FAMILY = "ORTHO"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"


def _return_pct(old, new):
    return (new / old - 1.0) * 100.0 if old > 0 else math.nan


def _at_or_before(history, when):
    answer = None
    for item in history:
        if item[0] <= when:
            answer = item
        else:
            break
    return answer


def _prices(history, timestamp, minutes):
    result = []
    for ago in range(minutes, -1, -1):
        item = _at_or_before(history, timestamp - timedelta(minutes=ago))
        if item is None:
            return None
        result.append(float(item[1]))
    return result


def _r2(values):
    n = len(values)
    if n < 3:
        return 0.0
    sx = n * (n - 1) / 2.0
    sy = sum(values)
    sxx = sum(i * i for i in range(n))
    sxy = sum(i * y for i, y in enumerate(values))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    mean = sy / n
    ss_tot = sum((y - mean) ** 2 for y in values)
    if ss_tot <= 0:
        return 0.0
    ss_res = sum((y - (intercept + slope * i)) ** 2 for i, y in enumerate(values))
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _p_candidate(history, timestamp):
    prices = _prices(history, timestamp, 33)
    if prices is None:
        return None
    pre = prices[:-3]
    pre_return = _return_pct(pre[0], pre[-1])
    pre_r2 = _r2(pre)
    flash = prices[-4:]
    start = flash[0]
    low = min(flash)
    current = flash[-1]
    drop = (start - low) / start * 100.0 if start > 0 else 0.0
    rebound = _return_pct(low, current)
    if pre_return < 0.75 or pre_r2 < 0.50 or drop < 1.0 or rebound < 0.10:
        return None
    target = low + 0.60 * (start - low)
    if target <= current:
        return None
    return {
        "entry_price": current,
        "target_price": target,
        "stop_price": current * 0.95,
        "pre_return_pct": pre_return,
        "pre_r2": pre_r2,
        "flash_drop_pct": drop,
        "rebound_pct": rebound,
    }


def _td_candidate(stock_history, spy_history, timestamp):
    stock = _prices(stock_history, timestamp, 30)
    spy = _prices(spy_history, timestamp, 30)
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


class PTD1XStrategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=45))

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol, quote in snapshot.quotes.items():
            self._history[symbol].append((snapshot.timestamp, float(quote.price), quote.total_volume))
        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        spy = self._history.get("SPY")
        local = snapshot.timestamp.astimezone(ZoneInfo("America/New_York"))
        minute_et = local.hour * 60 + local.minute
        out = []
        for symbol in snapshot.quotes:
            if symbol == "SPY":
                continue
            p = _p_candidate(self._history[symbol], snapshot.timestamp)
            td = None
            if spy is not None and 10 * 60 <= minute_et <= 11 * 60 + 30:
                td = _td_candidate(self._history[symbol], spy, snapshot.timestamp)
            if p is not None and td is not None:
                merged = dict(p)
                merged.update({f"td_{k}": v for k, v in td.items() if k not in {"entry_price", "target_price", "stop_price"}})
                out.append(_event(snapshot, symbol, "P_AND_TD1", merged))
            elif p is not None:
                out.append(_event(snapshot, symbol, "P", p))
            elif td is not None:
                out.append(_event(snapshot, symbol, "TD1", td))
        return out


def metadata():
    return {"strategy_id": STRATEGY_ID, "family": FAMILY, "paper_only": PAPER_ONLY, "forward_start_utc": FORWARD_START_UTC, "design": "self_contained_two_mode"}
