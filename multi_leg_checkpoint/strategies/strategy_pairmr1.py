"""Self-contained dynamic pair mean-reversion paper experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import math
import statistics

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "PAIRMR1"
FAMILY = "MULTI_LEG"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"

CANDIDATES = (
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV",
    "XLY", "XLP", "XLI", "XLU", "SMH", "IGV", "IYT", "XLB",
)
LOOKBACK = 60
MIN_CORR = 0.65
MIN_ABS_Z = 2.0
COOLDOWN_MINUTES = 30


def _corr(a, b):
    if len(a) != len(b) or len(a) < 10:
        return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    denom = math.sqrt(sum(x*x for x in da) * sum(x*x for x in db))
    return sum(x*y for x, y in zip(da, db)) / denom if denom > 0 else 0.0


def _returns(prices):
    return [b/a - 1.0 for a, b in zip(prices, prices[1:]) if a > 0]


def _residuals(a, b):
    # Fit log(B)=alpha+beta*log(A) locally; no other strategy/model is reused.
    x = [math.log(v) for v in a]
    y = [math.log(v) for v in b]
    mx, my = statistics.mean(x), statistics.mean(y)
    variance = sum((v-mx)**2 for v in x)
    if variance <= 0:
        return None
    beta = sum((u-mx)*(v-my) for u, v in zip(x, y)) / variance
    alpha = my - beta*mx
    return [v - (alpha + beta*u) for u, v in zip(x, y)]


class PAIRMR1Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=LOOKBACK+2))
        self._last_signal = None

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol in CANDIDATES:
            quote = snapshot.quotes.get(symbol)
            if quote is not None and quote.price > 0:
                self._history[symbol].append(float(quote.price))
        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        if self._last_signal is not None:
            if (snapshot.timestamp-self._last_signal).total_seconds() < COOLDOWN_MINUTES*60:
                return []

        available = [s for s in CANDIDATES if len(self._history[s]) >= LOOKBACK+1]
        best = None
        for i, left in enumerate(available):
            a = list(self._history[left])[-(LOOKBACK+1):]
            for right in available[i+1:]:
                b = list(self._history[right])[-(LOOKBACK+1):]
                corr = _corr(_returns(a), _returns(b))
                if corr < MIN_CORR:
                    continue
                residuals = _residuals(a, b)
                if residuals is None:
                    continue
                sd = statistics.pstdev(residuals[:-1])
                if sd <= 0:
                    continue
                z = (residuals[-1]-statistics.mean(residuals[:-1]))/sd
                if abs(z) < MIN_ABS_Z:
                    continue
                score = abs(z) * corr
                if best is None or score > best[0]:
                    best = (score, left, right, corr, z, a[-1], b[-1])
        if best is None:
            return []
        _, left, right, corr, z, left_px, right_px = best
        # Positive residual means right is rich relative to left.
        left_side, right_side = ("LONG", "SHORT") if z > 0 else ("SHORT", "LONG")
        self._last_signal = snapshot.timestamp
        return [SignalEvent(
            timestamp=snapshot.timestamp,
            strategy_id=STRATEGY_ID,
            symbol=f"{left}+{right}",
            signal_type="MULTI_LEG",
            data={
                "legs": [
                    {"symbol": left, "side": left_side, "weight": 0.5, "entry_price": left_px},
                    {"symbol": right, "side": right_side, "weight": 0.5, "entry_price": right_px},
                ],
                "take_profit_pct": 0.60,
                "stop_loss_pct": 0.60,
                "max_hold_minutes": 45,
                "setup": "dynamic_pair_residual_reversion",
                "paper_only": True,
                "live_order_placement": False,
                "forward_start_utc": FORWARD_START_UTC,
                "research": {"return_correlation": corr, "residual_z": z},
            },
        )]


def metadata():
    return {"strategy_id": STRATEGY_ID, "family": FAMILY, "paper_only": True, "forward_start_utc": FORWARD_START_UTC}
