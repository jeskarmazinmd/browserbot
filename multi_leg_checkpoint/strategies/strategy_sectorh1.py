"""Self-contained stock-versus-hedge relative-strength paper experiment."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


STRATEGY_ID = "SECTORH1"
FAMILY = "MULTI_LEG"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"
HEDGE = "QQQ"
STOCKS = (
    "NVDA", "AMD", "AVGO", "MSFT", "AAPL", "GOOGL", "META", "AMZN",
    "TSLA", "NFLX", "ORCL", "CRM", "ADBE", "INTC", "MU",
)
LOOKBACK = 30
MIN_ABS_EXCESS_PCT = 1.0
MIN_CONTINUATION_5M_PCT = 0.10
COOLDOWN_MINUTES = 30


def _return_pct(prices, minutes):
    if len(prices) < minutes+1 or prices[-minutes-1] <= 0:
        return None
    return (prices[-1]/prices[-minutes-1]-1.0)*100.0


class SECTORH1Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=LOOKBACK+2))
        self._last_signal = None

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        for symbol in (HEDGE, *STOCKS):
            quote = snapshot.quotes.get(symbol)
            if quote is not None and quote.price > 0:
                self._history[symbol].append(float(quote.price))
        if snapshot.timestamp.astimezone(timezone.utc) < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        if self._last_signal is not None and (snapshot.timestamp-self._last_signal).total_seconds() < COOLDOWN_MINUTES*60:
            return []
        hedge = self._history[HEDGE]
        if len(hedge) < LOOKBACK+1:
            return []
        hedge30 = _return_pct(hedge, 30)
        if hedge30 is None:
            return []
        best = None
        for symbol in STOCKS:
            hist = self._history[symbol]
            if len(hist) < LOOKBACK+1:
                continue
            ret30 = _return_pct(hist, 30)
            ret5 = _return_pct(hist, 5)
            if ret30 is None or ret5 is None:
                continue
            excess = ret30-hedge30
            # Require the short-term move to agree with the relative-strength side.
            if abs(excess) < MIN_ABS_EXCESS_PCT or abs(ret5) < MIN_CONTINUATION_5M_PCT or excess*ret5 <= 0:
                continue
            if best is None or abs(excess) > abs(best[0]):
                best = (excess, symbol, ret30, ret5)
        if best is None:
            return []
        excess, symbol, ret30, ret5 = best
        stock_side = "LONG" if excess > 0 else "SHORT"
        hedge_side = "SHORT" if excess > 0 else "LONG"
        self._last_signal = snapshot.timestamp
        return [SignalEvent(
            timestamp=snapshot.timestamp,
            strategy_id=STRATEGY_ID,
            symbol=f"{symbol}+{HEDGE}",
            signal_type="MULTI_LEG",
            data={
                "legs": [
                    {"symbol": symbol, "side": stock_side, "weight": 0.5, "entry_price": self._history[symbol][-1]},
                    {"symbol": HEDGE, "side": hedge_side, "weight": 0.5, "entry_price": hedge[-1]},
                ],
                "take_profit_pct": 0.75,
                "stop_loss_pct": 0.75,
                "max_hold_minutes": 60,
                "setup": "dynamic_relative_strength_with_hedge",
                "paper_only": True,
                "live_order_placement": False,
                "forward_start_utc": FORWARD_START_UTC,
                "research": {
                    "stock_return_30m_pct": ret30,
                    "stock_return_5m_pct": ret5,
                    "hedge_return_30m_pct": hedge30,
                    "excess_return_30m_pct": excess,
                },
            },
        )]


def metadata():
    return {"strategy_id": STRATEGY_ID, "family": FAMILY, "paper_only": True, "forward_start_utc": FORWARD_START_UTC}
