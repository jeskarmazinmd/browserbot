"""Deterministic executable-price state machine for C3N25S10.

This module has no networking, broker, filesystem, or wall-clock dependencies.
Callers provide quotes and timestamps; every state transition returns an event.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True)
class C3Config:
    rebound_fraction: float = 0.0025
    stop_fraction: float = 0.01
    activation_fraction: float = 0.003
    no_new_high_seconds: float = 30.0
    pending_timeout_seconds: float = 600.0
    order_latency_seconds: float = 0.250
    order_ttl_seconds: float = 2.0
    entry_limit_bps: float = 5.0
    stress_bps: float = 5.0
    max_quote_age_seconds: float = 2.5
    max_future_skew_seconds: float = 1.0
    max_spread_pct: float = 0.25
    minimum_remaining_upside_pct: float = 0.20
    starting_cash: float = 5000.0
    slot_notional: float = 1000.0

    def __post_init__(self) -> None:
        positive = (
            self.rebound_fraction, self.stop_fraction, self.activation_fraction,
            self.no_new_high_seconds, self.pending_timeout_seconds,
            self.order_latency_seconds, self.order_ttl_seconds,
            self.max_quote_age_seconds,
        )
        if any(not math.isfinite(x) or x <= 0 for x in positive):
            raise ValueError("C3 fractions and durations must be finite and positive")
        if self.order_ttl_seconds < self.order_latency_seconds:
            raise ValueError("order TTL cannot be shorter than simulated latency")
        if not 0 <= self.max_spread_pct < 100:
            raise ValueError("max spread must be in [0, 100)")
        nonnegative = (
            self.entry_limit_bps, self.stress_bps, self.max_future_skew_seconds,
            self.minimum_remaining_upside_pct,
        )
        if any(not math.isfinite(x) or x < 0 for x in nonnegative):
            raise ValueError("C3 execution thresholds must be finite and non-negative")
        if (not math.isfinite(self.starting_cash) or not math.isfinite(self.slot_notional)
                or self.starting_cash <= 0 or self.slot_notional <= 0):
            raise ValueError("cash and slot notional must be positive")


@dataclass(frozen=True)
class ExecutableQuote:
    symbol: str
    observed_at: float
    bid: float | None
    ask: float | None
    last: float | None = None
    mark: float | None = None
    quote_at: float | None = None
    bid_at: float | None = None
    ask_at: float | None = None
    realtime: bool | None = None

    @property
    def signal_price(self) -> float | None:
        if self.last and self.last > 0:
            return self.last
        if self.mark and self.mark > 0:
            return self.mark
        if self.bid and self.ask and self.bid > 0 and self.ask >= self.bid:
            return (self.bid + self.ask) / 2.0
        return None

    def side_time(self, side: str) -> float:
        value = self.ask_at if side == "ask" else self.bid_at
        return float(value or self.quote_at or self.observed_at)

    def fingerprint(self) -> tuple[Any, ...]:
        return (self.bid, self.ask, self.last, self.mark, self.quote_at, self.bid_at, self.ask_at)


@dataclass
class Pending:
    setup_id: str
    created_at: float
    lowest_signal: float
    target: float
    last_gate_reason: str | None = None


@dataclass
class EntryOrder:
    setup_id: str
    decision_at: float
    due_at: float
    expires_at: float
    limit: float
    target: float


@dataclass
class Position:
    setup_id: str
    entry_at: float
    entry_fill: float
    stress_entry: float
    shares: int
    cost: float
    target: float
    stop: float
    highest_bid: float
    highest_at: float
    activated: bool = False
    activation_at: float | None = None
    exit_due_at: float | None = None
    exit_reason: str | None = None
    last_gate_reason: str | None = None


class C3Logic:
    VERSION = 1

    def __init__(self, config: C3Config | None = None):
        self.config = config or C3Config()
        self.cash = self.config.starting_cash
        self.pending: dict[str, Pending] = {}
        self.orders: dict[str, EntryOrder] = {}
        self.positions: dict[str, Position] = {}
        self.seen: set[str] = set()
        self.last_observed_at: dict[str, float] = {}

    @staticmethod
    def _positive_finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and math.isfinite(float(value)) and value > 0

    @staticmethod
    def _event(kind: str, symbol: str, now: float, **fields: Any) -> dict[str, Any]:
        return {"event": kind, "symbol": symbol, "event_at": now, **fields}

    def _quote_gate(self, quote: ExecutableQuote, side: str) -> str | None:
        bid, ask = quote.bid, quote.ask
        if not self._positive_finite(bid):
            return "missing_or_crossed_quote"
        if side == "ask" and (not self._positive_finite(ask) or ask < bid):
            return "missing_or_crossed_quote"
        if side == "bid" and self._positive_finite(ask) and ask < bid:
            return "missing_or_crossed_quote"
        if quote.realtime is False:
            return "not_realtime"
        quote_at = quote.side_time(side)
        age = quote.observed_at - quote_at
        if age > self.config.max_quote_age_seconds:
            return "stale_quote"
        if age < -self.config.max_future_skew_seconds:
            return "future_quote"
        # Spread is an entry-quality constraint. A real sell must accept the
        # executable bid (including adverse liquidity) rather than hide it.
        if side == "ask" and (ask / bid - 1.0) * 100.0 > self.config.max_spread_pct:
            return "spread_too_wide"
        return None

    def register_signal(
        self,
        symbol: str,
        setup_id: str,
        target: float,
        quote: ExecutableQuote,
    ) -> list[dict[str, Any]]:
        symbol = symbol.upper()
        price = quote.signal_price
        if (
            not setup_id
            or quote.symbol.upper() != symbol
            or not self._positive_finite(target)
            or setup_id in self.seen
            or symbol in self.pending
            or symbol in self.orders
            or symbol in self.positions
            or not price
            or target <= price
        ):
            return []
        self.seen.add(setup_id)
        self.pending[symbol] = Pending(setup_id, quote.observed_at, price, float(target))
        return [self._event("SIGNAL", symbol, quote.observed_at, setup_id=setup_id, signal_price=price)]

    def on_quote(self, quote: ExecutableQuote, *, eod: bool = False) -> list[dict[str, Any]]:
        symbol = quote.symbol.upper()
        if not math.isfinite(quote.observed_at):
            return [self._event("QUOTE_IGNORED", symbol, 0.0, reason="invalid_observed_at")]
        previous = self.last_observed_at.get(symbol)
        if previous is not None and quote.observed_at < previous:
            return [self._event("QUOTE_IGNORED", symbol, quote.observed_at,
                                reason="observed_time_regressed", previous_observed_at=previous)]
        self.last_observed_at[symbol] = quote.observed_at
        events: list[dict[str, Any]] = []
        if symbol in self.pending:
            events.extend(self._advance_pending(symbol, quote))
        if symbol in self.orders:
            events.extend(self._advance_order(symbol, quote))
        if symbol in self.positions:
            events.extend(self._advance_position(symbol, quote, eod=eod))
        return events

    def _advance_pending(self, symbol: str, quote: ExecutableQuote) -> list[dict[str, Any]]:
        state = self.pending[symbol]
        now = quote.observed_at
        if now - state.created_at >= self.config.pending_timeout_seconds:
            del self.pending[symbol]
            return [self._event("ENTRY_REJECT", symbol, now, setup_id=state.setup_id, reason="rebound_timeout")]
        signal = quote.signal_price
        if not signal:
            return []
        state.lowest_signal = min(state.lowest_signal, signal)
        if signal / state.lowest_signal - 1.0 < self.config.rebound_fraction:
            return []
        reason = self._quote_gate(quote, "ask")
        if reason:
            if reason != state.last_gate_reason:
                state.last_gate_reason = reason
                return [self._event("ENTRY_GATE_BLOCK", symbol, now, setup_id=state.setup_id, reason=reason)]
            return []
        state.last_gate_reason = None
        ask = float(quote.ask)
        remaining = (state.target / ask - 1.0) * 100.0
        if remaining < self.config.minimum_remaining_upside_pct:
            del self.pending[symbol]
            return [self._event("ENTRY_REJECT", symbol, now, setup_id=state.setup_id,
                                reason="insufficient_ask_based_upside", remaining_upside_pct=remaining)]
        order = EntryOrder(
            setup_id=state.setup_id,
            decision_at=now,
            due_at=now + self.config.order_latency_seconds,
            expires_at=now + self.config.order_ttl_seconds,
            limit=ask * (1.0 + self.config.entry_limit_bps / 10000.0),
            target=state.target,
        )
        del self.pending[symbol]
        self.orders[symbol] = order
        return [self._event("ENTRY_DECISION", symbol, now, setup_id=state.setup_id,
                            bid=quote.bid, ask=ask, limit=order.limit)]

    def _advance_order(self, symbol: str, quote: ExecutableQuote) -> list[dict[str, Any]]:
        state = self.orders[symbol]
        now = quote.observed_at
        if now < state.due_at:
            return []
        reason = self._quote_gate(quote, "ask")
        ask = quote.ask
        if reason or not ask or ask > state.limit:
            if now < state.expires_at:
                return []
            del self.orders[symbol]
            return [self._event("ENTRY_REJECT", symbol, now, setup_id=state.setup_id,
                                reason=reason or "limit_not_filled")]
        fill = float(ask)
        budget = min(self.config.slot_notional, self.cash)
        shares = int(budget // fill)
        if shares < 1:
            del self.orders[symbol]
            return [self._event("ENTRY_REJECT", symbol, now, setup_id=state.setup_id,
                                reason="insufficient_cash")]
        cost = shares * fill
        self.cash -= cost
        bid = float(quote.bid)
        position = Position(
            setup_id=state.setup_id,
            entry_at=now,
            entry_fill=fill,
            stress_entry=fill * (1.0 + self.config.stress_bps / 10000.0),
            shares=shares,
            cost=cost,
            target=state.target,
            stop=fill * (1.0 - self.config.stop_fraction),
            highest_bid=bid,
            highest_at=now,
        )
        del self.orders[symbol]
        self.positions[symbol] = position
        return [self._event("ENTRY_FILL", symbol, now, setup_id=state.setup_id,
                            entry_fill=fill, bid=bid, shares=shares, cash=self.cash,
                            stop=position.stop)]

    def _advance_position(
        self,
        symbol: str,
        quote: ExecutableQuote,
        *,
        eod: bool,
    ) -> list[dict[str, Any]]:
        state = self.positions[symbol]
        now = quote.observed_at
        reason = self._quote_gate(quote, "bid")
        if reason:
            if reason != state.last_gate_reason:
                state.last_gate_reason = reason
                return [self._event("POSITION_QUOTE_BLOCK", symbol, now,
                                    setup_id=state.setup_id, reason=reason)]
            return []
        state.last_gate_reason = None
        bid = float(quote.bid)
        # Strategy timers measure when this process could act. Exchange/source
        # timestamps remain freshness evidence and must not move timers backward.
        event_time = now

        # A broker-held protective stop outranks a pending dynamic exit.
        if bid <= state.stop:
            return [self._close(symbol, quote, "STOP")]
        if eod:
            return [self._close(symbol, quote, "EOD")]

        # An exit decision is immutable. Do not move its due time on later polls.
        if state.exit_due_at is not None:
            if now >= state.exit_due_at:
                return [self._close(symbol, quote, state.exit_reason or "NO_NEW_HIGH")]
            return []

        if bid > state.highest_bid:
            state.highest_bid = bid
            state.highest_at = event_time
        activation_bid = state.entry_fill * (1.0 + self.config.activation_fraction)
        events: list[dict[str, Any]] = []
        if not state.activated and bid >= activation_bid:
            state.activated = True
            state.activation_at = event_time
            state.highest_bid = max(state.highest_bid, bid)
            state.highest_at = event_time
            events.append(self._event("ACTIVATED", symbol, now, setup_id=state.setup_id,
                                      bid=bid, activation_bid=activation_bid))
        if state.activated and event_time - state.highest_at >= self.config.no_new_high_seconds:
            state.exit_reason = "NO_NEW_HIGH"
            state.exit_due_at = now + self.config.order_latency_seconds
            events.append(self._event("EXIT_DECISION", symbol, now, setup_id=state.setup_id,
                                      reason=state.exit_reason, bid=bid,
                                      highest_bid=state.highest_bid,
                                      seconds_since_high=event_time - state.highest_at,
                                      due_at=state.exit_due_at))
        return events

    def _close(self, symbol: str, quote: ExecutableQuote, reason: str) -> dict[str, Any]:
        state = self.positions.pop(symbol)
        fill = float(quote.bid)
        proceeds = state.shares * fill
        self.cash += proceeds
        stress_exit = fill * (1.0 - self.config.stress_bps / 10000.0)
        pnl = (fill - state.entry_fill) * state.shares
        stress_pnl = (stress_exit - state.stress_entry) * state.shares
        return self._event(
            "EXIT_FILL", symbol, quote.observed_at, setup_id=state.setup_id, reason=reason,
            exit_fill=fill, stress_exit_fill=stress_exit, pnl=pnl, stress_pnl=stress_pnl,
            return_pct=(fill / state.entry_fill - 1.0) * 100.0,
            stress_return_pct=(stress_exit / state.stress_entry - 1.0) * 100.0,
            shares=state.shares, cash=self.cash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "cash": self.cash,
            "seen": sorted(self.seen),
            "last_observed_at": self.last_observed_at,
            "pending": {k: asdict(v) for k, v in self.pending.items()},
            "orders": {k: asdict(v) for k, v in self.orders.items()},
            "positions": {k: asdict(v) for k, v in self.positions.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], config: C3Config | None = None) -> "C3Logic":
        if int(payload.get("version", -1)) != cls.VERSION:
            raise ValueError("unsupported C3 state version")
        engine = cls(config)
        engine.cash = float(payload["cash"])
        if not math.isfinite(engine.cash) or engine.cash < 0:
            raise ValueError("invalid persisted cash")
        engine.seen = set(payload.get("seen", []))
        engine.last_observed_at = {
            str(k).upper(): float(v) for k, v in payload.get("last_observed_at", {}).items()
        }
        if any(not math.isfinite(v) for v in engine.last_observed_at.values()):
            raise ValueError("invalid persisted observation time")
        engine.pending = {k: Pending(**v) for k, v in payload.get("pending", {}).items()}
        engine.orders = {k: EntryOrder(**v) for k, v in payload.get("orders", {}).items()}
        engine.positions = {k: Position(**v) for k, v in payload.get("positions", {}).items()}
        occupied = list(engine.pending) + list(engine.orders) + list(engine.positions)
        if len(occupied) != len(set(occupied)):
            raise ValueError("symbol exists in multiple persisted states")
        if any(p.shares < 1 or p.cost <= 0 or p.entry_fill <= 0 for p in engine.positions.values()):
            raise ValueError("invalid persisted position")
        return engine
