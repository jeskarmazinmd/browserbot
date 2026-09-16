from pathlib import Path


ROOT = Path(__file__).resolve().parent
STRATEGIES = ROOT / "strategies"
TESTS = ROOT / "tests"
FORWARD_START = "2026-08-10T13:30:00+00:00"


def write(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n")
    print("WROTE", path)


def flash_module(
    strategy_id: str,
    description: str,
    family: str,
    *,
    pre_r2: float | None = None,
    target_max: float | None = None,
    midday: bool = False,
    rebound: float = 0.002,
    stop: float = 0.02,
    exit_model: str | None = None,
    activation: float | None = None,
    pullback: float | None = None,
    checkpoint: bool = False,
) -> str:
    extra_config = []
    if pre_r2 is not None:
        extra_config.append(f'    "min_pre_r2": {pre_r2!r},')
    if target_max is not None:
        extra_config.append(f'    "max_original_target_price": {target_max!r},')
    if midday:
        extra_config += ['    "start_minute_et": 720,', '    "end_minute_et": 840,']
    if activation is not None:
        extra_config.append(f'    "activation_gain_pct": {activation!r},')
    if pullback is not None:
        extra_config.append(f'    "pullback_from_high_pct": {pullback!r},')
    if checkpoint:
        extra_config += ['    "checkpoint_seconds": None,', '    "checkpoint_max_return_pct": None,']

    accept_extra = []
    if pre_r2 is not None:
        accept_extra += [
            '    if _num(event.get("pre_r2"), -1.0) < CONFIG["min_pre_r2"]:',
            '        return False',
        ]
    if target_max is not None:
        accept_extra += [
            '    if _num(event.get("target_price"), float("inf")) > CONFIG["max_original_target_price"]:',
            '        return False',
        ]
    accept_extra.append("    return True")

    refresh_extra = []
    if exit_model is not None:
        refresh_extra.append(f'        "exit_model": {exit_model!r},')
    if activation is not None:
        refresh_extra.append('        "activation_gain_pct": CONFIG["activation_gain_pct"],')
    if pullback is not None:
        refresh_extra.append('        "pullback_from_high_pct": CONFIG["pullback_from_high_pct"],')
    if checkpoint:
        refresh_extra += [
            '        "checkpoint_seconds": CONFIG["checkpoint_seconds"],',
            '        "checkpoint_max_return_pct": CONFIG["checkpoint_max_return_pct"],',
        ]

    validate_extra = []
    if midday:
        validate_extra += [
            "    minute = _minute_et(event)",
            '    if minute is None or not (CONFIG["start_minute_et"] <= minute < CONFIG["end_minute_et"]):',
            '        return False, "outside_midday_window"',
        ]

    return f'''\
"""Independent prospective paper experiment: {description}."""

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

STRATEGY_ID = {strategy_id!r}
DESCRIPTION = {description!r}
FAMILY = {family!r}
PAPER_ONLY = True
FORWARD_START_UTC = {FORWARD_START!r}

CONFIG = {{
    "flash_drop_pct": 1.0,
    "rebound_confirmation_pct": {rebound!r},
    "stop_loss_fraction": {stop!r},
    "live_order_placement": False,
{chr(10).join(extra_config)}
}}


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _timestamp(event):
    for key in ("timestamp", "signal_window_end", "detected_at"):
        value = event.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _minute_et(event):
    timestamp = _timestamp(event)
    if timestamp is None:
        return None
    local = timestamp.astimezone(ZoneInfo("America/New_York"))
    return local.hour * 60 + local.minute


def accepts_flash(event: Mapping[str, Any], max_flash_drop_pct: float) -> bool:
    drop = _num(event.get("flash_drop_pct"), -1.0)
    if not (CONFIG["flash_drop_pct"] <= drop <= float(max_flash_drop_pct)):
        return False
{chr(10).join(accept_extra)}


def refresh_event_for_entry(event: Mapping[str, Any], current_price: float) -> dict[str, Any]:
    refreshed = dict(event)
    entry = float(current_price)
    original_target = float(refreshed["target_price"])
    original_drop = float(refreshed["flash_drop_pct"])
    remaining = ((original_target / entry) - 1.0) * 100.0
    refreshed.update({{
        "strategy_id": STRATEGY_ID,
        "entry_price": entry,
        "original_flash_drop_pct": original_drop,
        "original_target_price": original_target,
        "remaining_upside_pct": remaining,
        "target_price": original_target,
        "stop_price": entry * (1.0 - CONFIG["stop_loss_fraction"]),
        "rebound_confirmation_pct": CONFIG["rebound_confirmation_pct"] * 100.0,
        "stop_loss_fraction": CONFIG["stop_loss_fraction"],
        "paper_only": True,
        "live_order_placement": False,
        "forward_start_utc": FORWARD_START_UTC,
{chr(10).join(refresh_extra)}
    }})
    return refreshed


def validate_confirmed_entry(event: Mapping[str, Any], min_remaining_upside_pct: float) -> tuple[bool, str | None]:
    entry = _num(event.get("entry_price"))
    target = _num(event.get("target_price"))
    original_drop = _num(event.get("original_flash_drop_pct", event.get("flash_drop_pct")))
    remaining = _num(event.get("remaining_upside_pct"), -999.0)
    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < float(min_remaining_upside_pct):
        return False, "insufficient_remaining_upside"
{chr(10).join(validate_extra)}
    timestamp = _timestamp(event)
    birth = datetime.fromisoformat(FORWARD_START_UTC)
    if timestamp is None or timestamp.astimezone(timezone.utc) < birth:
        return False, "before_forward_start"
    return True, None


def metadata() -> dict[str, Any]:
    return {{
        "strategy_id": STRATEGY_ID,
        "description": DESCRIPTION,
        "family": FAMILY,
        "paper_only": PAPER_ONLY,
        "forward_start_utc": FORWARD_START_UTC,
        "config": dict(CONFIG),
    }}
'''


def ema_module(
    strategy_id: str,
    description: str,
    *,
    max_target: float | None = None,
    volume_ratio: float = 1.20,
    target_pct: float = 0.75,
    stop_pct: float = 0.55,
) -> str:
    target_guard = ""
    if max_target is not None:
        target_guard = f'''\
            prospective_target = price * (1.0 + TARGET_PCT / 100.0)
            if prospective_target > MAX_ORIGINAL_TARGET_PRICE:
                continue
'''
    max_line = f"MAX_ORIGINAL_TARGET_PRICE = {max_target!r}\n" if max_target is not None else ""
    return f'''\
"""Independent prospective EMA1-family experiment: {description}."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import boolean, consider, minimum, reset
from .snapshot_common import make_signal

STRATEGY_ID = {strategy_id!r}
DESCRIPTION = {description!r}
FAMILY = "EMA1X"
PAPER_ONLY = True
FORWARD_START_UTC = {FORWARD_START!r}
FAST_SPAN = 9
SLOW_SPAN = 21
MIN_VOLUME_RATIO = {volume_ratio!r}
TARGET_PCT = {target_pct!r}
STOP_PCT = {stop_pct!r}
{max_line}


@dataclass
class _State:
    observations_seen: int = 0
    fast: float | None = None
    slow: float | None = None
    prior_fast: float | None = None
    prior_slow: float | None = None


class Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._state: dict[str, _State] = {{}}

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        signals = []
        reset(self)
        birth = datetime.fromisoformat(FORWARD_START_UTC)
        stamp = snapshot.timestamp
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(timezone.utc) < birth:
            return signals
        volume_provider = snapshot.metadata.get("confirm_recent_volume_ratio")

        for symbol, quote in snapshot.quotes.items():
            state = self._state.setdefault(symbol, _State())
            price = float(quote.price)
            state.prior_fast = state.fast
            state.prior_slow = state.slow
            if state.fast is None:
                state.fast = price
                state.slow = price
            else:
                fast_alpha = 2.0 / (FAST_SPAN + 1.0)
                slow_alpha = 2.0 / (SLOW_SPAN + 1.0)
                state.fast = fast_alpha * price + (1.0 - fast_alpha) * state.fast
                state.slow = slow_alpha * price + (1.0 - slow_alpha) * state.slow
            state.observations_seen += 1
            if state.observations_seen < SLOW_SPAN + 3:
                continue
            crossed = (
                state.prior_fast is not None
                and state.prior_slow is not None
                and state.prior_fast <= state.prior_slow
                and state.fast > state.slow
            )
            consider(self, symbol, snapshot.timestamp, price, [
                boolean("bullish_ema_crossover", crossed),
                boolean("volume_provider_available", callable(volume_provider)),
            ])
            if not crossed or not callable(volume_provider):
                continue
{target_guard}            try:
                latest_volume_ratio = volume_provider(symbol)
            except Exception:
                latest_volume_ratio = None
            consider(self, symbol, snapshot.timestamp, price, [
                minimum("volume_ratio", latest_volume_ratio, MIN_VOLUME_RATIO),
            ])
            if latest_volume_ratio is None or float(latest_volume_ratio) < MIN_VOLUME_RATIO:
                continue
            signals.append(make_signal(
                snapshot,
                STRATEGY_ID,
                symbol,
                price,
                TARGET_PCT,
                STOP_PCT,
                "ema_9_21_bullish_crossover",
                ema_9=state.fast,
                ema_21=state.slow,
                prior_ema_9=state.prior_fast,
                prior_ema_21=state.prior_slow,
                latest_volume_ratio=float(latest_volume_ratio),
                minimum_volume_ratio=MIN_VOLUME_RATIO,
                forward_start_utc=FORWARD_START_UTC,
                sampling_model="completed_minute_discrete_ema",
                volume_model="lazy_schwab_completed_minute_ratio",
            ))
        return signals
'''


FLASH = {
    "strategy_c1f1mid.py": flash_module(
        "C1F1MID", "C1F1 rules restricted to midday", "C1F1X",
        pre_r2=0.50, midday=True, exit_model="c1", activation=0.3, pullback=0.2,
    ),
    "strategy_c1f1r65.py": flash_module(
        "C1F1R65", "C1F1 rules with pre-trend R2 >= 0.65", "C1F1X",
        pre_r2=0.65, exit_model="c1", activation=0.3, pullback=0.2,
    ),
    "strategy_c1f1pb15.py": flash_module(
        "C1F1PB15", "C1F1 rules with 0.15 percent trailing pullback", "C1F1X",
        pre_r2=0.50, exit_model="c1", activation=0.3, pullback=0.15,
    ),
    "strategy_j2t15.py": flash_module(
        "J2T15", "Independent J2 entry with original target <= 14.822", "J2X",
        target_max=14.822, stop=0.005, exit_model="checkpoint_target_stop_eod", checkpoint=True,
    ),
    "strategy_j2mid.py": flash_module(
        "J2MID", "Independent J2 entry restricted to midday", "J2X",
        midday=True, stop=0.005, exit_model="checkpoint_target_stop_eod", checkpoint=True,
    ),
    "strategy_j2rb30.py": flash_module(
        "J2RB30", "Independent J2 entry with 0.30 percent rebound confirmation", "J2X",
        rebound=0.003, stop=0.005, exit_model="checkpoint_target_stop_eod", checkpoint=True,
    ),
}

EMA = {
    "strategy_ema1t50.py": ema_module(
        "EMA1T50", "EMA1 with original target <= 50.687325", max_target=50.687325,
    ),
    "strategy_ema1v15.py": ema_module(
        "EMA1V15", "EMA1 with volume ratio >= 1.50", volume_ratio=1.50,
    ),
    "strategy_ema1rr.py": ema_module(
        "EMA1RR", "EMA1 with 0.90 percent target and 0.45 percent stop",
        target_pct=0.90, stop_pct=0.45,
    ),
}


def patch_registry() -> None:
    p = STRATEGIES / "registry.py"
    s = p.read_text()

    import_anchor = "from . import strategy_c1f1\n"
    import_add = (
        "from . import strategy_c1f1\n"
        "from . import strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15\n"
        "from . import strategy_j2t15, strategy_j2mid, strategy_j2rb30\n"
    )
    if "strategy_c1f1mid" not in s:
        if import_anchor not in s:
            raise SystemExit("registry flash import anchor missing")
        s = s.replace(import_anchor, import_add, 1)

    tuple_anchor = "        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,\n"
    tuple_add = (
        "        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,\n"
        "        strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15,\n"
        "        strategy_j2t15, strategy_j2mid, strategy_j2rb30,\n"
    )
    if "strategy_c1f1mid, strategy_c1f1r65" not in s:
        if tuple_anchor not in s:
            raise SystemExit("registry flash tuple anchor missing")
        s = s.replace(tuple_anchor, tuple_add, 1)

    class_anchor = '    ("strategy_ema1", "EMA1Strategy"),\n'
    class_add = (
        '    ("strategy_ema1", "EMA1Strategy"),\n'
        '    ("strategy_ema1t50", "Strategy"),\n'
        '    ("strategy_ema1v15", "Strategy"),\n'
        '    ("strategy_ema1rr", "Strategy"),\n'
    )
    if '"strategy_ema1t50"' not in s:
        if class_anchor not in s:
            raise SystemExit("registry EMA class anchor missing")
        s = s.replace(class_anchor, class_add, 1)

    p.write_text(s)
    print("UPDATED", p)


TEST = r'''
import importlib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from engine.events import MarketSnapshot, Quote
from strategies.registry import FLASH_STRATEGY_MODULES, MINUTE_STRATEGIES


FLASH_IDS = {"C1F1MID", "C1F1R65", "C1F1PB15", "J2T15", "J2MID", "J2RB30"}
EMA_IDS = {"EMA1T50", "EMA1V15", "EMA1RR"}


def flash_event(timestamp="2026-08-10T16:30:00+00:00"):
    return {
        "symbol": "XYZ",
        "timestamp": timestamp,
        "signal_window_end": timestamp,
        "flash_drop_pct": 1.2,
        "pre_r2": 0.8,
        "target_price": 10.0,
        "entry_price": 9.5,
        "flash_start_price": 10.4,
    }


class IndependentNextFamiliesTests(unittest.TestCase):
    def test_flash_children_are_direct_and_paper_only(self):
        self.assertTrue(FLASH_IDS <= set(FLASH_STRATEGY_MODULES))
        for strategy_id in FLASH_IDS:
            module = FLASH_STRATEGY_MODULES[strategy_id]
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.CONFIG["live_order_placement"])
            self.assertEqual(module.FORWARD_START_UTC, "2026-08-10T13:30:00+00:00")

    def test_new_children_do_not_import_parent_modules(self):
        for strategy_id in FLASH_IDS | EMA_IDS:
            source = Path("strategies") / f"strategy_{strategy_id.lower()}.py"
            text = source.read_text().lower()
            for forbidden in ("strategy_c1f1", "strategy_ema1", "strategy_j2", "strategy_b"):
                self.assertNotIn(f"import {forbidden}", text)
                self.assertNotIn(f"from . import {forbidden}", text)

    def test_j2t15_has_independent_entry_filter(self):
        module = FLASH_STRATEGY_MODULES["J2T15"]
        self.assertTrue(module.accepts_flash(flash_event(), 12.0))
        high = flash_event()
        high["target_price"] = 20.0
        self.assertFalse(module.accepts_flash(high, 12.0))

    def test_c1f1_variants_own_r2_and_exit_rules(self):
        event = flash_event()
        self.assertTrue(FLASH_STRATEGY_MODULES["C1F1R65"].accepts_flash(event, 12.0))
        event["pre_r2"] = 0.60
        self.assertFalse(FLASH_STRATEGY_MODULES["C1F1R65"].accepts_flash(event, 12.0))
        refreshed = FLASH_STRATEGY_MODULES["C1F1PB15"].refresh_event_for_entry(flash_event(), 9.6)
        self.assertEqual(refreshed["exit_model"], "c1")
        self.assertEqual(refreshed["pullback_from_high_pct"], 0.15)

    def test_midday_uses_confirmed_entry_time(self):
        module = FLASH_STRATEGY_MODULES["C1F1MID"]
        refreshed = module.refresh_event_for_entry(flash_event(), 9.6)
        refreshed["timestamp"] = "2026-08-10T16:30:00+00:00"  # 12:30 ET
        self.assertTrue(module.validate_confirmed_entry(refreshed, 0.20)[0])
        refreshed["timestamp"] = "2026-08-10T14:30:00+00:00"  # 10:30 ET
        self.assertFalse(module.validate_confirmed_entry(refreshed, 0.20)[0])

    def test_ema_children_are_direct_minute_strategies(self):
        minute_ids = {getattr(x, "name", "") for x in MINUTE_STRATEGIES}
        self.assertTrue(EMA_IDS <= minute_ids)

    def test_ema_children_are_forward_gated(self):
        module = importlib.import_module("strategies.strategy_ema1v15")
        strategy = module.Strategy()
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc),
            quotes={"XYZ": Quote(price=100.0)},
            expected_symbol_count=1,
            returned_symbol_count=1,
            fetch_duration_seconds=0.1,
            metadata={"confirm_recent_volume_ratio": lambda symbol: 2.0},
        )
        self.assertEqual(strategy.on_snapshot(snap), [])


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not STRATEGIES.exists() or not TESTS.exists():
        raise SystemExit("Run this installer from the browserbot repository root")
    for name, source in {**FLASH, **EMA}.items():
        write(STRATEGIES / name, source)
    patch_registry()
    write(TESTS / "test_next_independent_families.py", TEST)


if __name__ == "__main__":
    main()
