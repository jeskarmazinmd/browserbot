"""Independent prospective GT1-like trend + M-like VWAP reversal experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "GTMX"
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


def _items(history, timestamp, minutes):
    result = []
    for ago in range(minutes, -1, -1):
        item = _at_or_before(history, timestamp - timedelta(minutes=ago))
        if item is None:
            return None
        result.append(item)
    return result


def _r2(values):
    n = len(values)
    sx = n * (n - 1) / 2.0
    sy = sum(values)
    sxx = sum(i * i for i in range(n))
    sxy = sum(i * y for i, y in enumerate(values))
    denom = n * sxx - sx * sx
    if n < 3 or denom == 0:
        return 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    mean = sy / n
    total = sum((y - mean) ** 2 for y in values)
    if total <= 0:
        return 0.0
    residual = sum((y - intercept - slope * i) ** 2 for i, y in enumerate(values))
    return max(0.0, min(1.0, 1.0 - residual / total))


def _gt_candidate(history, timestamp):
    items = _items(history, timestamp, 30)
    if items is None:
        return None
    prices = [float(x[1]) for x in items]
    ret30 = _return_pct(prices[0], prices[-1])
    r2 = _r2(prices)
    up_fraction = sum(b > a for a, b in zip(prices, prices[1:])) / 30.0
    if ret30 < 0.60 or r2 < 0.35 or up_fraction < 0.52:
        return None
    price = prices[-1]
    return {
        "entry_price": price,
        "target_price": price * 1.007,
        "stop_price": price * 0.993,
        "trend_return_30m_pct": ret30,
        "trend_r2": r2,
        "trend_up_minute_fraction": up_fraction,
    }


def _rolling_vwap(items):
    weighted = 0.0
    volume = 0.0
    for previous, current in zip(items, items[1:]):
        if previous[2] is None or current[2] is None:
            continue
        dv = float(current[2]) - float(previous[2])
        if dv <= 0:
            continue
        weighted += float(current[1]) * dv
        volume += dv
    return weighted / volume if volume > 0 else None


def _m_candidate(history, timestamp):
    items = _items(history, timestamp, 45)
    if items is None:
        return None
    vwap = _rolling_vwap(items)
    if vwap is None or vwap <= 0:
        return None
    prices = [float(x[1]) for x in items]
    current = prices[-1]
    distance = (vwap - current) / vwap * 100.0
    flash = prices[-4:]
    start = flash[0]
    low = min(flash)
    drop = (start - low) / start * 100.0 if start > 0 else 0.0
    rebound = _return_pct(low, current)
    if distance < 0.50 or drop < 1.0 or rebound < 0.10:
        return None
    target = low + 0.60 * (start - low)
    if target <= current:
        return None
    return {
        "entry_price": current,
        "target_price": target,
        "stop_price": current * 0.95,
        "rolling_vwap_45m": vwap,
        "distance_below_rolling_vwap_pct": distance,
        "flash_drop_pct": drop,
        "rebound_pct": rebound,
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


class GTMXStrategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=50))

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol, quote in snapshot.quotes.items():
            self._history[symbol].append((snapshot.timestamp, float(quote.price), quote.total_volume))
        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        out = []
        for symbol in snapshot.quotes:
            if symbol == "SPY":
                continue
            gt = _gt_candidate(self._history[symbol], snapshot.timestamp)
            m = _m_candidate(self._history[symbol], snapshot.timestamp)
            if gt is not None and m is not None:
                merged = dict(gt)
                merged.update({f"m_{k}": v for k, v in m.items() if k not in {"entry_price", "target_price", "stop_price"}})
                out.append(_event(snapshot, symbol, "GT_AND_M", merged))
            elif gt is not None:
                out.append(_event(snapshot, symbol, "GT", gt))
            elif m is not None:
                out.append(_event(snapshot, symbol, "M", m))
        return out


def metadata():
    return {"strategy_id": STRATEGY_ID, "family": FAMILY, "paper_only": PAPER_ONLY, "forward_start_utc": FORWARD_START_UTC, "design": "self_contained_two_mode"}
