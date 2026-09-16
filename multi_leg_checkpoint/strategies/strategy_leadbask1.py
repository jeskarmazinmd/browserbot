"""Self-contained dynamic lead/lag follower-basket paper experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import math
import statistics

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "LEADBASK1"
FAMILY = "MULTI_LEG"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"
CANDIDATES = (
    "SPY", "QQQ", "XLK", "SMH", "NVDA", "AMD", "AVGO", "MSFT",
    "AAPL", "GOOGL", "META", "AMZN", "TSLA", "NFLX", "ORCL", "CRM",
)
LOOKBACK = 45
MIN_LAG_CORR = 0.25
MIN_HALF_CORR = 0.10
MIN_LEADER_MOVE_PCT = 0.30
COOLDOWN_MINUTES = 20


def _corr(a, b):
    if len(a) != len(b) or len(a) < 8:
        return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    da, db = [x-ma for x in a], [x-mb for x in b]
    denom = math.sqrt(sum(x*x for x in da)*sum(x*x for x in db))
    return sum(x*y for x, y in zip(da, db))/denom if denom > 0 else 0.0


def _returns(prices):
    return [b/a-1.0 for a, b in zip(prices, prices[1:]) if a > 0]


class LEADBASK1Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=LOOKBACK+3))
        self._last_signal = None

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol in CANDIDATES:
            quote = snapshot.quotes.get(symbol)
            if quote is not None and quote.price > 0:
                self._history[symbol].append(float(quote.price))
        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        if self._last_signal is not None and (snapshot.timestamp-self._last_signal).total_seconds() < COOLDOWN_MINUTES*60:
            return []
        available = [s for s in CANDIDATES if len(self._history[s]) >= LOOKBACK+2]
        relationships = {}
        for leader in available:
            leader_r = _returns(list(self._history[leader])[-(LOOKBACK+2):])
            for follower in available:
                if follower == leader:
                    continue
                follower_r = _returns(list(self._history[follower])[-(LOOKBACK+2):])
                x, y = leader_r[:-1], follower_r[1:]
                corr = _corr(x, y)
                half = len(x)//2
                if corr < MIN_LAG_CORR or _corr(x[:half], y[:half]) < MIN_HALF_CORR or _corr(x[half:], y[half:]) < MIN_HALF_CORR:
                    continue
                relationships.setdefault(leader, []).append((corr, follower))

        best = None
        for leader, followers in relationships.items():
            prices = list(self._history[leader])
            move = (prices[-1]/prices[-2]-1.0)*100.0
            if abs(move) < MIN_LEADER_MOVE_PCT:
                continue
            followers = sorted(followers, reverse=True)[:2]
            if len(followers) < 2:
                continue
            score = abs(move)*sum(x[0] for x in followers)
            if best is None or score > best[0]:
                best = (score, leader, move, followers)
        if best is None:
            return []
        _, leader, move, followers = best
        side = "LONG" if move > 0 else "SHORT"
        legs = []
        for corr, follower in followers:
            legs.append({
                "symbol": follower,
                "side": side,
                "weight": 0.5,
                "entry_price": self._history[follower][-1],
            })
        self._last_signal = snapshot.timestamp
        return [SignalEvent(
            timestamp=snapshot.timestamp,
            strategy_id=STRATEGY_ID,
            symbol="+".join(x["symbol"] for x in legs),
            signal_type="MULTI_LEG",
            data={
                "legs": legs,
                "take_profit_pct": 0.50,
                "stop_loss_pct": 0.50,
                "max_hold_minutes": 30,
                "setup": "dynamic_leader_two_follower_basket",
                "paper_only": True,
                "live_order_placement": False,
                "forward_start_utc": FORWARD_START_UTC,
                "research": {
                    "leader": leader,
                    "leader_last_move_pct": move,
                    "lag_correlations": {f: c for c, f in followers},
                },
            },
        )]


def metadata():
    return {"strategy_id": STRATEGY_ID, "family": FAMILY, "paper_only": True, "forward_start_utc": FORWARD_START_UTC}
