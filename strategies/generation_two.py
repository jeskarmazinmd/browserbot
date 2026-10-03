"""Frozen G2 flash experiments. Source labels never invoke G1/source signals."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo

SOURCE_COMMIT = "e69344d8cb2705002e718699ab6c4f3ae877f274"
CREATED_UTC = "2026-10-03T13:36:00+00:00"
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
    max_entry_spread_pct: float = math.inf
    min_target_spread_multiple: float = 0.0
    min_executable_upside_pct: float = .20
    portfolio_risk_fraction: float | None = None
    one_position_per_symbol: bool = False
    comparison_id: str = ""

P_GAIN = Rule("PT315G1525", "P", checkpoint_seconds=900)
Q_QUALITY = Rule("QV4XU1S50V8", "Q", max_units=8.0, min_upside=1.0, max_spread=.50)

_catalog = []
for prefix, rule in (("PG", P_GAIN), ("QV", Q_QUALITY)):
    control = "G2" + prefix + "CTL"
    def add(suffix, hypothesis, **parameters):
        _catalog.append(Experiment("G2" + prefix + suffix, hypothesis,
                                   (rule,), 1, parameters.pop("exit_rule", rule),
                                   comparison_id=parameters.pop("comparison_id", control), **parameters))
    add("CTL", "Frozen " + rule.source + "; $1000 orders, $5000 prospective control")
    for spread in (.05, .10, .20, .30):
        add("S" + str(round(spread * 100)), f"Executable spread <= {spread:g}%; same admission and exit",
            max_entry_spread_pct=spread)
    for multiple in (2, 3, 5, 8):
        add("E" + str(multiple), f"Executable target distance >= {multiple} times bid/ask spread; opportunity filter",
            min_target_spread_multiple=float(multiple))
    for upside in ((.5, 1.0, 1.5, 2.0) if prefix == "PG" else (1.25, 1.5, 2.0, 3.0)):
        add("U" + str(round(upside * 100)), f"Executable target upside >= {upside:g}%; same exit",
            min_executable_upside_pct=upside)
    for seconds in (300, 600, 1200, 1800):
        add("K" + str(seconds // 60), f"Require 0.25% observed BID gain by {seconds // 60}m; same stop/target",
            exit_rule=replace(rule, checkpoint_seconds=seconds))
    for stop in (.02, .03, .04):
        add("D" + str(round(stop * 100)), f"{stop * 100:g}% disaster stop; same admission and target/checkpoint",
            exit_rule=replace(rule, stop=stop))
    for scale in (.50, .65, .75):
        add("T" + str(round(scale * 100)), f"Target at {scale * 100:g}% of original recovery distance; same checkpoint/stop",
            exit_rule=replace(rule, target_scale=scale))
    for risk in (.001, .002, .005):
        add("R" + str(round(risk * 10000)), f"Per-order nominal stop risk {risk * 100:g}% of cost equity; 20% position cap",
            risk_fraction=risk)
    for cap in (.05, .10, .15):
        add("C" + str(round(cap * 100)), f"Fixed order capped at {cap * 100:g}% of initial $5000 cash",
            notional=5000 * cap)
    for budget in (.01, .02):
        add("B" + str(round(budget * 100)), f"Total open nominal stop risk <= {budget * 100:g}% of cost equity; 0.5% per order",
            risk_fraction=.005, portfolio_risk_fraction=budget, comparison_id="G2" + prefix + "R50")
    add("ONE", "One active position per symbol, including residual partial exits; otherwise control sizing",
        one_position_per_symbol=True)

CATALOG = tuple(_catalog)
IDS = frozenset(spec.strategy_id for spec in CATALOG)
assert len(CATALOG) == len(IDS) == 64
_SPEC_BY_ID = {spec.strategy_id: spec for spec in CATALOG}


def spec_for(sid):
    return _SPEC_BY_ID[sid]


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
    return {
        "strategy_id": sid, "description": spec.hypothesis, "family": "GENERATION_TWO",
        "paper_only": True, "generation": 2,
        "source_strategy_ids": list(dict.fromkeys(rule.source for rule in (*spec.rules, spec.exit_rule))),
        "created_utc": CREATED_UTC, "source_commit": SOURCE_COMMIT,
        "comparison_id": spec.comparison_id,
        "parameters": parameter_snapshot(asdict(spec)),
        "prospective_start_policy": "durable first tracker activation; never backfilled",
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
        self.__name__ = f"strategies.generation_two.{sid}"

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
                   forward_start_utc=CREATED_UTC, rule_version="generation_two_frozen_v1",
                   research_generation=2, research_metadata=metadata(sid))
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
