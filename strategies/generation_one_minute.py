"""Owned minute history and frozen TRENDX2/BRK20 predicates for generation 1."""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import timedelta

from engine.events import SignalEvent
from .event_base import EventStrategy
from .generation_one import CREATED_UTC, SOURCE_COMMIT, timestamp

# Copied literally; no runtime reference to either source module.
UNIVERSE = ('SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLU', 'SMH', 'IYT', 'GLD', 'SLV', 'USO', 'TLT', 'NVDA', 'AMD', 'AVGO', 'MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NFLX', 'ORCL', 'CRM', 'MU', 'INTC')


@dataclass(frozen=True)
class MinuteExperiment:
    strategy_id: str
    hypothesis: str
    rules: tuple[str, ...]
    votes: int
    target: float
    stop: float
    notional: float = 1000.0
    ret30: float = 1.2
    ret5: float = .25
    up_fraction: float = .58
    window: int = 20
    range_pct: float = 1.5
    buffer: float = .1


CATALOG = (
    MinuteExperiment("G1TB2", "Same-symbol trend AND bounded 20m breakout; trend 0.9% target/0.65% stop", ("TREND", "BREAK"), 2, .9, .65),
    MinuteExperiment("G1TBU", "Deduplicated trend OR bounded breakout; uniform trend exit policy", ("TREND", "BREAK"), 1, .9, .65),
    MinuteExperiment("G1TN500", "Frozen trend $500 orders in a $5k cash portfolio", ("TREND",), 1, .9, .65, 500),
    MinuteExperiment("G1TN1500", "Frozen trend $1500 orders in a $5k cash portfolio", ("TREND",), 1, .9, .65, 1500),
    MinuteExperiment("G1BN500", "Frozen breakout $500 orders in a $5k cash portfolio", ("BREAK",), 1, .7, .55, 500),
    MinuteExperiment("G1BN1500", "Frozen breakout $1500 orders in a $5k cash portfolio", ("BREAK",), 1, .7, .55, 1500),
    MinuteExperiment("G1TB150", "Trend 30m return >=1.5% rather than 1.2%; other parameters frozen", ("TREND",), 1, .9, .65, ret30=1.5),
    MinuteExperiment("G1BB15", "Breakout buffer 0.15% rather than 0.10%; bounded range unchanged", ("BREAK",), 1, .7, .55, buffer=.15),
)
IDS = frozenset(spec.strategy_id for spec in CATALOG)


def spec_for(sid):
    return next(spec for spec in CATALOG if spec.strategy_id == sid)


def metadata(sid):
    spec = spec_for(sid)
    return {"strategy_id": sid, "description": spec.hypothesis, "family": "GENERATION_ONE",
            "paper_only": True, "generation": 1, "source_strategy_ids": [{"TREND": "TRENDX2", "BREAK": "BRK20"}[kind] for kind in spec.rules],
            "created_utc": CREATED_UTC, "source_commit": SOURCE_COMMIT,
            "parameters": {**asdict(spec), "universe": list(UNIVERSE), "max_history": 66},
            "prospective_start_policy": "durable first tracker activation; never backfilled",
            "config": {"live_order_placement": False}}


def predicates(spec, prices):
    votes, score, metrics = [], 0.0, {}
    if "TREND" in spec.rules and len(prices) >= 31:
        r30 = (prices[-1] / prices[-31] - 1) * 100
        r5 = (prices[-1] / prices[-6] - 1) * 100
        up = sum(b > a for a, b in zip(prices[-31:], prices[-30:])) / 30
        if r30 >= spec.ret30 and r5 >= spec.ret5 and up >= spec.up_fraction:
            votes.append("TRENDX2")
            score = max(score, r5)
        metrics.update(return_30m_pct=r30, return_5m_pct=r5, up_fraction=up)
    if "BREAK" in spec.rules and len(prices) >= spec.window + 1:
        prior = prices[-spec.window - 1:-1]
        hi, lo = max(prior), min(prior)
        width = (hi / lo - 1) * 100
        breakout = (prices[-1] / hi - 1) * 100
        if width <= spec.range_pct and prices[-1] >= hi * (1 + spec.buffer / 100):
            votes.append("BRK20")
            score = max(score, breakout)
        metrics.update(prior_range_pct=width, breakout_pct=breakout)
    return votes, score, metrics


class FrozenMinuteStrategy(EventStrategy):
    PAPER_ONLY = True

    def __init__(self):
        self._history = defaultdict(lambda: deque(maxlen=66))
        self._last = {}

    def on_snapshot(self, snapshot):
        spec = spec_for(self.name)
        candidates = []
        for symbol in UNIVERSE:
            quote = snapshot.quotes.get(symbol)
            if quote is None or quote.price <= 0:
                continue
            last = self._last.get(symbol)
            if last is not None and snapshot.timestamp <= last:
                continue
            if last is not None and snapshot.timestamp - last != timedelta(minutes=1):
                self._history[symbol].clear()
            self._last[symbol] = snapshot.timestamp
            self._history[symbol].append(float(quote.price))
            if snapshot.timestamp < timestamp(CREATED_UTC):
                continue
            votes, score, metrics = predicates(spec, list(self._history[symbol]))
            if len(votes) >= spec.votes:
                candidates.append((score, symbol, quote.price, votes, metrics))
        if not candidates:
            return []
        # Like the sources: only one highest-score candidate per module/minute.
        _, symbol, price, votes, metrics = max(candidates, key=lambda row: row[0])
        return [SignalEvent(snapshot.timestamp, self.name, symbol, "SIGNAL", {
            "entry_price": price, "target_price": price * (1 + spec.target / 100),
            "stop_price": price * (1 - spec.stop / 100), "paper_only": True,
            "live_order_placement": False, "forward_start_utc": CREATED_UTC,
            "experimental_child": True, "rule_version": "generation_one_frozen_v1",
            "research_generation": 1, "research_metadata": metadata(self.name),
            "constituent_votes": votes, **metrics,
        })]


# Stable named classes are importable by persistent minute worker shards.
for _spec in CATALOG:
    globals()[_spec.strategy_id + "Strategy"] = type(
        _spec.strategy_id + "Strategy", (FrozenMinuteStrategy,),
        {"name": _spec.strategy_id, "__module__": __name__},
    )


class FrozenMinuteModule:
    PAPER_ONLY = True

    def __init__(self, sid):
        self.STRATEGY_ID = sid
        self.__name__ = __name__
        self.Strategy = globals()[sid + "Strategy"]

    @property
    def CONFIG(self):
        return metadata(self.STRATEGY_ID)["config"]

    def metadata(self):
        return metadata(self.STRATEGY_ID)


MODULES = {sid: FrozenMinuteModule(sid) for sid in sorted(IDS)}
