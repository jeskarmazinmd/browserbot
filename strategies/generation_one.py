"""Frozen first-generation research rules; never import source strategies.

Source IDs are lineage labels only. Consensus means same raw candidate,
same symbol, same confirmation, with votes re-evaluated at executable ASK.
Each experiment owns one order and one explicitly specified exit policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo

SOURCE_COMMIT = "8698eeeb254fa2df642b367c9cf26ae10feb5c26"
CREATED_UTC = "2026-09-30T19:02:10+00:00"
NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Rule:
    source: str
    kind: str
    min_units: float = 4.25
    max_units: float = math.inf
    min_upside: float = 0.0
    max_spread: float = math.inf
    max_price: float = math.inf
    midday: bool = False
    stop: float = .05
    target_scale: float = 1.0
    checkpoint_seconds: int = 0
    required_gain: float = .25


# Literal snapshots of the selected source rules at SOURCE_COMMIT.
P_GAIN = Rule("PT315G1525", "P", checkpoint_seconds=900)
P_TARGET = Rule("PT315T75", "P", target_scale=.75)
P_LOW = Rule("PT315PLOW", "P", max_price=5.0)
P_STOP = Rule("PT315S30", "P", stop=.03)
MIDDAY = Rule("PMID", "M", midday=True)
Q_QUALITY = Rule("QV4XU1S50V8", "Q", max_units=8.0, min_upside=1.0, max_spread=.50)
Q_STOP = Rule("QV4XU1S3", "Q", min_upside=1.0, stop=.03)
Q_BAND = Rule("QV4VB608", "Q", min_units=6.0, max_units=8.0)
Q_UP = Rule("QV4UP125", "Q", min_upside=1.25)
TREND = Rule("TRENDX2", "T")


@dataclass(frozen=True)
class Experiment:
    strategy_id: str
    hypothesis: str
    rules: tuple[Rule, ...]
    votes: int
    exit_rule: Rule
    notional: float = 1000.0
    equity: float = 5000.0
    risk_fraction: float | None = None
    max_position_fraction: float = .20
    agreement_weighted: bool = False


_catalog = [
    Experiment("G1PQG", "P gain-checkpoint entry plus Q upside/spread/volatility quality; P 15m gain exit", (P_GAIN, Q_QUALITY), 2, P_GAIN),
    Experiment("G1PQT", "P reduced-target entry plus Q >=1% upside/3% stop admission; P 75% target exit", (P_TARGET, Q_STOP), 2, P_TARGET),
    Experiment("G1MQ", "Midday P confirmation plus Q 6-8 volatility band; 5% stop/original target", (MIDDAY, Q_BAND), 2, MIDDAY),
    Experiment("G1LQ", "P <=$5 confirmation plus Q >=1.25% executable upside; 5% stop/original target", (P_LOW, Q_UP), 2, P_LOW),
    Experiment("G1PQ2", "2-of-3 P gain, Q quality, midday P admission with uniform P gain exit; time stratification", (P_GAIN, Q_QUALITY, MIDDAY), 2, P_GAIN),
    Experiment("G1PQ3", "3-of-3 P gain, Q quality, midday P admission with uniform P gain exit; stricter time/quality intersection", (P_GAIN, Q_QUALITY, MIDDAY), 3, P_GAIN),
    Experiment("G1PQU", "Deduplicated P gain OR Q quality admission with uniform P gain exit", (P_GAIN, Q_QUALITY), 1, P_GAIN),
    Experiment("G1PGS3", "P gain checkpoint with 3% rather than 5% disaster stop", (P_GAIN,), 1, replace(P_GAIN, stop=P_STOP.stop)),
    Experiment("G1QVS3", "Q quality entry with 3% rather than 5% stop", (Q_QUALITY,), 1, replace(Q_QUALITY, stop=Q_STOP.stop)),
    Experiment("G1PGT75", "P gain checkpoint combined with 75% target distance", (P_GAIN,), 1, replace(P_GAIN, target_scale=P_TARGET.target_scale)),
    Experiment("G1PG10", "P gain requirement assessed at 10m rather than 15m", (P_GAIN,), 1, replace(P_GAIN, checkpoint_seconds=600)),
    Experiment("G1PG20", "P gain requirement assessed at 20m rather than 15m", (P_GAIN,), 1, replace(P_GAIN, checkpoint_seconds=1200)),
    Experiment("G1QVU125", "Q quality entry with 1.25% rather than 1% executable upside", (replace(Q_QUALITY, min_upside=1.25),), 1, Q_QUALITY),
]
for _prefix, _rule in (("PG", P_GAIN), ("QV", Q_QUALITY)):
    for _amount in (500, 1000, 1500, 2500):
        _catalog.append(Experiment(f"G1{_prefix}N{_amount}", f"{_rule.source} fixed ${_amount} order; capacity and $5k cash competition", (_rule,), 1, _rule, float(_amount)))
_catalog.extend((
    Experiment("G1QQ2", "Within-Q quality AND 6-8 volatility band; quality exit policy", (Q_QUALITY, Q_BAND), 2, Q_QUALITY),
    Experiment("G1PQ34", "3-of-4 P gain, Q quality, Q 6-8 band, midday P; uniform P gain exit", (P_GAIN, Q_QUALITY, Q_BAND, MIDDAY), 3, P_GAIN),
    Experiment("G1PQUW", "P/Q union: $1000 for one vote, $2000 for two votes; one deduplicated order", (P_GAIN, Q_QUALITY), 1, P_GAIN, agreement_weighted=True),
    Experiment("G1PQW2", "P/Q agreement: $2000 only on two votes; compare G1PQG fixed $1000", (P_GAIN, Q_QUALITY), 2, P_GAIN, agreement_weighted=True),
    Experiment("G1PQT2", "Flash-triggered 2-of-3 P 75% target, Q >=1% upside/3% stop admission, fresh completed-minute trend; uniform P 75% target exit", (P_TARGET, Q_STOP, TREND), 2, P_TARGET),
    Experiment("G1PQT3", "Flash-triggered 3-of-3 P 75% target, Q >=1% upside/3% stop admission, fresh completed-minute trend; uniform P 75% target exit", (P_TARGET, Q_STOP, TREND), 3, P_TARGET),
    Experiment("G1PGRCTL", "Frozen P gain $5k portfolio, 1% equity stop risk, 20% position cap", (P_GAIN,), 1, P_GAIN, risk_fraction=.01),
    Experiment("G1QVRCTL", "Frozen Q quality $5k portfolio, 1% equity stop risk, 20% position cap", (Q_QUALITY,), 1, Q_QUALITY, risk_fraction=.01),
    Experiment("G1PGCCTL", "P gain plus 3% stop: $5k, 1% equity risk, 20% cap; matched cap-sweep control", (P_GAIN,), 1, replace(P_GAIN, stop=.03), risk_fraction=.01),
))
for _equity in (2500, 10000, 25000):
    _catalog.append(Experiment(f"G1PGE{_equity}", f"P gain portfolio ${_equity}; 1% stop risk and 20% cap unchanged", (P_GAIN,), 1, P_GAIN, equity=float(_equity), risk_fraction=.01))
for _risk in (.001, .002, .005):
    _catalog.append(Experiment(f"G1PGR{int(_risk * 10000)}", f"P gain ${5000} portfolio with {_risk * 100:.2f}% equity stop risk and 20% cap", (P_GAIN,), 1, P_GAIN, risk_fraction=_risk))
for _cap in (.05, .10, .15, .25, .33):
    _catalog.append(Experiment(f"G1PGC{int(_cap * 100)}", f"P gain plus 3% stop, $5k portfolio, 1% equity stop risk, {_cap * 100:g}% position cap", (P_GAIN,), 1, replace(P_GAIN, stop=.03), risk_fraction=.01, max_position_fraction=_cap))
_catalog.extend((
    Experiment("G1QVR20", "Q quality $5k portfolio, 0.20% equity stop risk, 20% cap; cross-family risk check", (Q_QUALITY,), 1, Q_QUALITY, risk_fraction=.002),
    Experiment("G1QVC10", "Q quality $5k portfolio, 1% equity stop risk, 10% cap; cross-family cap check", (Q_QUALITY,), 1, Q_QUALITY, risk_fraction=.01, max_position_fraction=.10),
))
CATALOG = tuple(_catalog)
IDS = frozenset(spec.strategy_id for spec in CATALOG)


def spec_for(sid):
    return next(spec for spec in CATALOG if spec.strategy_id == sid)


def num(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def raw_vote(rule, event, maximum):
    drop = num(event.get("flash_drop_pct"), -1)
    if not 1.0 <= drop <= maximum:
        return False
    if rule.kind == "T":
        # Raw admission only creates owned pending state. The T vote requires
        # a fresh completed-minute observation at confirmation and execution.
        return True
    if rule.kind in {"P", "M"}:
        if num(event.get("pre_return_pct"), -1e99) < .75 or num(event.get("pre_r2"), -1e99) < .5:
            return False
        if rule.kind == "P" and not 3.25 <= num(event.get("original_target_price", event.get("target_price"))) <= 31.5:
            return False
    else:
        std = num(event.get("pre30_return_std_pct"))
        units = drop / std if std > 0 else 0.0
        if not rule.min_units <= units <= rule.max_units:
            return False
    return True


def entry_vote(rule, event, price, spread):
    if rule.kind == "T":
        return event.get("frozen_trend_vote") is True
    if price <= 0 or price > rule.max_price:
        return False
    if rule.midday:
        ts = timestamp(event.get("timestamp"))
        if ts is None:
            return False
        et = ts.astimezone(NY)
        if not 720 <= et.hour * 60 + et.minute < 840:
            return False
    original = num(event.get("original_target_price", event.get("target_price")))
    return (original / price - 1) * 100 >= rule.min_upside and spread <= rule.max_spread


def executable_votes(sid, event, ask, bid):
    """Recount votes at ASK, so union/voting gates are never over-intersected."""
    spread = (ask / bid - 1) * 100 if bid > 0 else math.inf
    ts = timestamp(event.get("timestamp"))
    trend_ts = timestamp(event.get("frozen_trend_timestamp"))
    trend_fresh = (ts is not None and trend_ts is not None
                   and 0 < (ts - trend_ts).total_seconds() <= 120)
    reference = num(event.get("entry_price"))
    original = num(event.get("original_target_price", event.get("target_price")))
    return tuple(rule.source for rule in spec_for(sid).rules
                 if raw_vote(rule, event, num(event.get("research_max_flash_drop_pct"), 12.0))
                 and entry_vote(rule, event, ask, spread)
                 and (rule.kind == "T" or (
                     reference > 0 and bid > reference * (1 - rule.stop)
                     and ask < reference + (original - reference) * rule.target_scale))
                 and (rule.kind != "T" or trend_fresh))


def metadata(sid):
    spec = spec_for(sid)
    sources = tuple(dict.fromkeys(rule.source for rule in (*spec.rules, spec.exit_rule)))
    if sid == "G1PGS3" or sid.startswith("G1PGC"):
        sources += (P_STOP.source,)
    if sid == "G1QVS3":
        sources += (Q_STOP.source,)
    if sid == "G1PGT75":
        sources += (P_TARGET.source,)
    return {
        "strategy_id": sid, "description": spec.hypothesis, "family": "GENERATION_ONE",
        "paper_only": True, "generation": 1, "source_strategy_ids": list(sources),
        "created_utc": CREATED_UTC, "source_commit": SOURCE_COMMIT,
        "parameters": parameter_snapshot(asdict(spec)), "prospective_start_policy": "durable first tracker activation; never backfilled",
        "config": {"flash_drop_pct": 1.0, "rebound_confirmation_pct": .001,
                   "pending_rebound_timeout_seconds": 600, "min_remaining_upside_pct": .20,
                   "stop_loss_fraction": spec.exit_rule.stop, "live_order_placement": False},
    }


def parameter_snapshot(value):
    """Strict JSON metadata uses an explicit sentinel for unbounded axes."""
    if isinstance(value, float) and not math.isfinite(value):
        return "unbounded"
    if isinstance(value, dict):
        return {key: parameter_snapshot(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [parameter_snapshot(item) for item in value]
    return value


class FrozenFlashModule:
    PAPER_ONLY = True

    def __init__(self, sid):
        self.STRATEGY_ID = sid
        self.__name__ = f"strategies.generation_one.{sid}"

    @property
    def CONFIG(self):
        return metadata(self.STRATEGY_ID)["config"]

    def metadata(self):
        return metadata(self.STRATEGY_ID)

    def accepts_flash(self, event, maximum):
        spec = spec_for(self.STRATEGY_ID)
        return sum(raw_vote(rule, event, maximum) for rule in spec.rules) >= spec.votes

    def refresh_event_for_entry(self, event, price):
        sid = self.STRATEGY_ID
        spec = spec_for(sid)
        policy = spec.exit_rule
        original = float(event["target_price"])
        row = dict(event)
        row.update(strategy_id=sid, entry_price=price, original_target_price=original,
                   original_flash_drop_pct=event["flash_drop_pct"],
                   target_price=price + (original - price) * policy.target_scale,
                   stop_price=price * (1 - policy.stop), stop_loss_fraction=policy.stop,
                   remaining_upside_pct=(original / price - 1) * 100,
                   paper_only=True, live_order_placement=False, experimental_child=True,
                   forward_start_utc=CREATED_UTC, rule_version="generation_one_frozen_v1",
                   research_generation=1, research_metadata=metadata(sid))
        if policy.checkpoint_seconds:
            row.update(exit_model="k_checkpoint", mode="conditional_reach",
                       seconds=policy.checkpoint_seconds, required_gain_pct=policy.required_gain)
        else:
            row["exit_model"] = "target_stop_eod"
        return row

    def validate_confirmed_entry(self, event, minimum):
        ts = timestamp(event.get("timestamp"))
        if ts is None or ts < timestamp(CREATED_UTC):
            return False, "before_prospective_start"
        price = num(event.get("entry_price"))
        target = num(event.get("target_price"))
        if price <= 0 or target <= price:
            return False, "target_reached_before_entry"
        if (target / price - 1) * 100 < .20:
            return False, "insufficient_remaining_upside"
        # Executable spread/upside votes are deliberately deferred to the BA tracker.
        spec = spec_for(self.STRATEGY_ID)
        count = sum(raw_vote(rule, event, 12.0) for rule in spec.rules)
        return (True, None) if count >= spec.votes else (False, "insufficient_confirmation_votes")


MODULES = {sid: FrozenFlashModule(sid) for sid in sorted(IDS)}
