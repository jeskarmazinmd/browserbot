"""Shared bounded mechanics for paper-only SPY strategy experiments."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from zoneinfo import ZoneInfo

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import boolean, consider, minimum, reset
from .snapshot_common import Observation, make_signal, value_at_or_before


NY = ZoneInfo("America/New_York")
SPY = "SPY"
RESEARCH_FORWARD_START_UTC = "2026-08-05T13:30:00+00:00"


def _return_pct(old: float | None, new: float | None) -> float | None:
    if old is None or new is None or old <= 0:
        return None
    return (new / old - 1.0) * 100.0


def _at(history: deque[Observation], timestamp, minutes_ago: int) -> float | None:
    item = value_at_or_before(history, timestamp - timedelta(minutes=minutes_ago))
    return float(item.price) if item is not None else None


def _minute_et(snapshot: MarketSnapshot) -> int:
    local = snapshot.timestamp.astimezone(NY)
    return local.hour * 60 + local.minute


def _regular_session(snapshot: MarketSnapshot) -> bool:
    minute = _minute_et(snapshot)
    return 9 * 60 + 30 <= minute < 16 * 60


class _SPYHistoryStrategy(EventStrategy):
    """Retain only the symbols needed by one SPY hypothesis."""

    required_symbols = frozenset({SPY})
    history_minutes = 35

    def __init__(self):
        self._session_date = None
        self._history = defaultdict(deque)

    def _prepare(self, snapshot: MarketSnapshot) -> bool:
        reset(self)
        local = snapshot.timestamp.astimezone(NY)
        if local.date() != self._session_date:
            self._session_date = local.date()
            self._history.clear()

        for symbol in self.required_symbols:
            quote = snapshot.quotes.get(symbol)
            if quote is None:
                continue
            history = self._history[symbol]
            history.append(Observation(snapshot.timestamp, float(quote.price), None))
            cutoff = snapshot.timestamp - timedelta(minutes=self.history_minutes)
            while len(history) > 1 and history[1].timestamp < cutoff:
                history.popleft()
        return _regular_session(snapshot) and SPY in snapshot.quotes

    def _spy_price(self, snapshot: MarketSnapshot) -> float:
        return float(snapshot.quotes[SPY].price)


class OpeningRangeSPYStrategy(_SPYHistoryStrategy):
    range_minutes = 15
    entry_end_minute_et = 11 * 60
    break_buffer_pct = 0.05
    target_pct = 0.50
    stop_pct = 0.30

    def __init__(self):
        super().__init__()
        self._opening_prices = []

    def _prepare(self, snapshot: MarketSnapshot) -> bool:
        prior_date = self._session_date
        ready = super()._prepare(snapshot)
        if self._session_date != prior_date:
            self._opening_prices = []
        return ready

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot):
            return []
        minute = _minute_et(snapshot)
        range_end = 9 * 60 + 30 + self.range_minutes
        price = self._spy_price(snapshot)

        if 9 * 60 + 30 <= minute < range_end:
            self._opening_prices.append(price)
            return []
        if minute < range_end or minute > self.entry_end_minute_et or not self._opening_prices:
            return []

        high = max(self._opening_prices)
        low = min(self._opening_prices)
        breakout = _return_pct(high, price)
        breakout = float("nan") if breakout is None else breakout
        consider(
            self, SPY, snapshot.timestamp, price,
            [minimum("breakout_pct", breakout, self.break_buffer_pct, "%")],
            metrics={"opening_high": high, "opening_low": low},
        )
        if breakout < self.break_buffer_pct:
            return []

        return [make_signal(
            snapshot, self.name, SPY, price, self.target_pct, self.stop_pct,
            f"spy_opening_range_{self.range_minutes}m_breakout",
            opening_range_minutes=self.range_minutes,
            opening_high=high,
            opening_low=low,
            breakout_pct=breakout,
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]


class SPYMomentumStrategy(_SPYHistoryStrategy):
    min_return_5m_pct = 0.08
    min_return_15m_pct = 0.15
    target_pct = 0.45
    stop_pct = 0.30

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot) or not (9 * 60 + 45 <= _minute_et(snapshot) <= 15 * 60):
            return []
        price = self._spy_price(snapshot)
        history = self._history[SPY]
        ret5 = _return_pct(_at(history, snapshot.timestamp, 5), price)
        ret15 = _return_pct(_at(history, snapshot.timestamp, 15), price)
        if ret5 is None or ret15 is None:
            return []
        rules = [
            minimum("return_5m_pct", ret5, self.min_return_5m_pct, "%"),
            minimum("return_15m_pct", ret15, self.min_return_15m_pct, "%"),
        ]
        consider(self, SPY, snapshot.timestamp, price, rules)
        if ret5 < self.min_return_5m_pct or ret15 < self.min_return_15m_pct:
            return []
        return [make_signal(
            snapshot, self.name, SPY, price, self.target_pct, self.stop_pct,
            "spy_intraday_momentum", return_5m_pct=ret5, return_15m_pct=ret15,
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]


class SPYMeanReversionStrategy(_SPYHistoryStrategy):
    min_depth_pct = 0.30
    min_rebound_2m_pct = 0.05
    target_pct = 0.35
    stop_pct = 0.30

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot) or not (10 * 60 <= _minute_et(snapshot) <= 15 * 60):
            return []
        history = self._history[SPY]
        if len(history) < 20:
            return []
        price = self._spy_price(snapshot)
        recent = [item.price for item in list(history)[-20:]]
        mean20 = sum(recent) / len(recent)
        depth = (mean20 / price - 1.0) * 100.0
        rebound2 = _return_pct(_at(history, snapshot.timestamp, 2), price)
        if rebound2 is None:
            return []
        rules = [
            minimum("depth_below_mean_pct", depth, self.min_depth_pct, "%"),
            minimum("rebound_2m_pct", rebound2, self.min_rebound_2m_pct, "%"),
        ]
        consider(self, SPY, snapshot.timestamp, price, rules)
        if depth < self.min_depth_pct or rebound2 < self.min_rebound_2m_pct:
            return []
        return [make_signal(
            snapshot, self.name, SPY, price, self.target_pct, self.stop_pct,
            "spy_intraday_mean_reversion", rolling_mean_20m=mean20,
            depth_below_mean_pct=depth, rebound_2m_pct=rebound2,
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]


class _BreadthMixin:
    breadth_lookback_minutes = 5

    def __init__(self):
        super().__init__()
        self._breadth_history = defaultdict(deque)

    def _prepare(self, snapshot: MarketSnapshot) -> bool:
        prior_date = self._session_date
        ready = super()._prepare(snapshot)
        if self._session_date != prior_date:
            self._breadth_history.clear()
        cutoff = snapshot.timestamp - timedelta(minutes=self.breadth_lookback_minutes + 1)
        for symbol, quote in snapshot.quotes.items():
            history = self._breadth_history[symbol]
            history.append(Observation(snapshot.timestamp, float(quote.price), None))
            while len(history) > 1 and history[1].timestamp < cutoff:
                history.popleft()
        return ready

    def _breadth_pct(self, snapshot: MarketSnapshot) -> float | None:
        advancing = 0
        observed = 0
        for symbol, history in self._breadth_history.items():
            old = _at(history, snapshot.timestamp, self.breadth_lookback_minutes)
            quote = snapshot.quotes.get(symbol)
            if old is None or quote is None or old <= 0:
                continue
            observed += 1
            advancing += float(quote.price) > old
        return advancing / observed * 100.0 if observed else None


class SPYBreadthStrategy(_BreadthMixin, SPYMomentumStrategy):
    min_breadth_pct = 58.0

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot) or not (9 * 60 + 45 <= _minute_et(snapshot) <= 15 * 60):
            return []
        price = self._spy_price(snapshot)
        history = self._history[SPY]
        ret5 = _return_pct(_at(history, snapshot.timestamp, 5), price)
        breadth = self._breadth_pct(snapshot)
        if ret5 is None or breadth is None:
            return []
        rules = [
            minimum("spy_return_5m_pct", ret5, self.min_return_5m_pct, "%"),
            minimum("advancing_breadth_5m_pct", breadth, self.min_breadth_pct, "%"),
        ]
        consider(self, SPY, snapshot.timestamp, price, rules)
        if ret5 < self.min_return_5m_pct or breadth < self.min_breadth_pct:
            return []
        return [make_signal(
            snapshot, self.name, SPY, price, 0.45, 0.30,
            "spy_breadth_confirmed_momentum", spy_return_5m_pct=ret5,
            advancing_breadth_5m_pct=breadth,
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]


class SPYCrossAssetStrategy(_SPYHistoryStrategy):
    required_symbols = frozenset({SPY, "QQQ", "IWM", "HYG", "LQD", "UUP"})

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot) or not (9 * 60 + 45 <= _minute_et(snapshot) <= 15 * 60):
            return []
        if any(symbol not in snapshot.quotes for symbol in self.required_symbols):
            return []
        returns = {}
        for symbol in self.required_symbols:
            current = float(snapshot.quotes[symbol].price)
            returns[symbol] = _return_pct(_at(self._history[symbol], snapshot.timestamp, 5), current)
        if any(value is None for value in returns.values()):
            return []
        credit_excess = returns["HYG"] - returns["LQD"]
        confirmations = {
            "spy_positive": returns[SPY] >= 0.05,
            "qqq_positive": returns["QQQ"] > 0.0,
            "iwm_positive": returns["IWM"] > 0.0,
            "credit_supportive": credit_excess >= -0.02,
            "dollar_not_surging": returns["UUP"] <= 0.08,
        }
        price = self._spy_price(snapshot)
        rules = [boolean(name, value) for name, value in confirmations.items()]
        consider(self, SPY, snapshot.timestamp, price, rules)
        if not all(confirmations.values()):
            return []
        return [make_signal(
            snapshot, self.name, SPY, price, 0.45, 0.30,
            "spy_cross_asset_risk_on", spy_return_5m_pct=returns[SPY],
            qqq_return_5m_pct=returns["QQQ"], iwm_return_5m_pct=returns["IWM"],
            hyg_lqd_excess_5m_pct=credit_excess, uup_return_5m_pct=returns["UUP"],
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]


class SPYEnsembleStrategy(_BreadthMixin, _SPYHistoryStrategy):
    required_symbols = SPYCrossAssetStrategy.required_symbols
    min_score = 4

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        if not self._prepare(snapshot) or not (10 * 60 <= _minute_et(snapshot) <= 15 * 60):
            return []
        if any(symbol not in snapshot.quotes for symbol in self.required_symbols):
            return []
        price = self._spy_price(snapshot)
        spy_history = self._history[SPY]
        ret5 = _return_pct(_at(spy_history, snapshot.timestamp, 5), price)
        ret15 = _return_pct(_at(spy_history, snapshot.timestamp, 15), price)
        breadth = self._breadth_pct(snapshot)
        qqq5 = _return_pct(_at(self._history["QQQ"], snapshot.timestamp, 5), float(snapshot.quotes["QQQ"].price))
        iwm5 = _return_pct(_at(self._history["IWM"], snapshot.timestamp, 5), float(snapshot.quotes["IWM"].price))
        hyg5 = _return_pct(_at(self._history["HYG"], snapshot.timestamp, 5), float(snapshot.quotes["HYG"].price))
        lqd5 = _return_pct(_at(self._history["LQD"], snapshot.timestamp, 5), float(snapshot.quotes["LQD"].price))
        if any(value is None for value in (ret5, ret15, breadth, qqq5, iwm5, hyg5, lqd5)):
            return []
        components = {
            "spy_5m": ret5 >= 0.05,
            "spy_15m": ret15 >= 0.10,
            "breadth": breadth >= 55.0,
            "qqq": qqq5 > 0.0,
            "iwm": iwm5 > 0.0,
            "credit": (hyg5 - lqd5) >= -0.02,
        }
        score = sum(components.values())
        rules = [minimum("ensemble_score", score, self.min_score)]
        consider(self, SPY, snapshot.timestamp, price, rules, metrics=components)
        if score < self.min_score:
            return []
        return [make_signal(
            snapshot, self.name, SPY, price, 0.50, 0.30,
            "spy_multi_factor_ensemble", ensemble_score=score,
            ensemble_components=components, spy_return_5m_pct=ret5,
            spy_return_15m_pct=ret15, advancing_breadth_5m_pct=breadth,
            forward_start_utc=RESEARCH_FORWARD_START_UTC,
        )]
