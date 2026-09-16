#!/usr/bin/env python3
"""Find capacity-efficient admission rules for high-volume paper strategies.

This is an offline research tool.  It never changes strategy state or places
orders.  It joins archived SIGNAL events to PAPER_EXIT outcomes, discovers
simple rules on training days, and evaluates them on held-out days.
"""
from __future__ import annotations

import argparse
import gc
import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
DEFAULT_STRATEGIES = (
    "GR1,VWEMA1,SMA1,BO1,AV1,EMA3,HL1,QTD1X,PTD1X,GTMX"
)
KEEP_FRACTIONS = (0.05, 0.10, 0.20, 0.30, 0.50)
TOP_NS = (1, 3, 5, 10)
COOLDOWN_MINUTES = (15, 30, 60, 120)


def utc(value: Any) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        from datetime import timezone
        result = result.replace(tzinfo=timezone.utc)
    return result


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def flatten(prefix: str, value: Any, output: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            flatten(f"{prefix}.{key}" if prefix else str(key), child, output)
    elif isinstance(value, (str, bool)) or finite_number(value):
        output[prefix] = value


def event_paths(root: Path) -> list[Path]:
    paths = [root / "bot_events.jsonl"]
    paths.extend((root / "archive").glob("bot_events*.jsonl.gz"))
    paths.extend((root / "archive" / "intraday").glob("**/*.jsonl.gz"))
    return sorted({path for path in paths if path.exists()}, key=str)


def rows_from(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                yield row


@dataclass
class Trade:
    setup_id: str
    strategy: str
    symbol: str
    day: str
    entry_at: datetime
    exit_at: datetime
    pnl: float
    return_pct: float
    reason: str
    features: dict[str, Any]


@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    predicate: Callable[[Trade], bool]


def signal_features(row: dict[str, Any]) -> dict[str, Any]:
    signal = row.get("signal") or {}
    regime = row.get("signal_regime") or {}
    features: dict[str, Any] = {}
    flatten("signal", signal, features)
    flatten("regime", regime, features)

    memberships = signal.get("universe_memberships") or []
    for membership in memberships:
        features[f"membership.{membership}"] = True

    try:
        stamp = utc(signal.get("timestamp") or row.get("timestamp")).astimezone(NY)
        minute = stamp.hour * 60 + stamp.minute
        features["time.minute_et"] = minute
        features["time.hour_et"] = stamp.hour
        features["time.minutes_from_open"] = minute - (9 * 60 + 30)
    except Exception:
        pass

    entry = signal.get("entry_price")
    target = signal.get("target_price")
    stop = signal.get("stop_price")
    if finite_number(entry) and float(entry) > 0:
        entry = float(entry)
        features["derived.log10_entry_price"] = math.log10(entry)
        if finite_number(target):
            features["derived.target_pct"] = (float(target) / entry - 1.0) * 100.0
        if finite_number(stop):
            features["derived.stop_pct"] = (float(stop) / entry - 1.0) * 100.0
    return features


def load_signals(root: Path, strategies: set[str], days: set[str]) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    for path in event_paths(root):
        for row in rows_from(path):
            if row.get("event_type") != "SIGNAL":
                continue
            signal = row.get("signal") or {}
            strategy = str(row.get("strategy_id") or signal.get("strategy_id") or "")
            setup_id = str(signal.get("setup_id") or "")
            day = str(signal.get("timestamp") or row.get("timestamp") or "")[:10]
            if strategy not in strategies or not setup_id or day not in days:
                continue
            signals.setdefault(setup_id, {
                "strategy": strategy,
                "symbol": str(signal.get("symbol") or row.get("symbol") or ""),
                "day": day,
                "features": signal_features(row),
            })
    return signals


def load_trades(root: Path, signals: dict[str, dict[str, Any]]) -> list[Trade]:
    trades: list[Trade] = []
    paths = [root / "paper_signal_outcomes.jsonl"]
    paths.extend(sorted((root / "archive").glob("paper_trades*.jsonl.gz")))
    seen: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for row in rows_from(path):
            if row.get("event_type") != "PAPER_EXIT":
                continue
            setup_id = str(row.get("setup_id") or "")
            source = signals.get(setup_id)
            if source is None or setup_id in seen:
                continue
            try:
                entry_at = utc(row.get("entry_timestamp") or row.get("signal_timestamp"))
                exit_at = utc(row["exit_timestamp"])
                pnl = float(row.get("pnl", 0) or 0)
                ret = float(row.get("return_pct", 0) or 0)
            except (ValueError, TypeError, KeyError):
                continue
            seen.add(setup_id)
            trades.append(Trade(
                setup_id=setup_id,
                strategy=source["strategy"],
                symbol=source["symbol"],
                day=source["day"],
                entry_at=entry_at,
                exit_at=exit_at,
                pnl=pnl,
                return_pct=ret,
                reason=str(row.get("exit_reason") or "UNKNOWN"),
                features=source["features"],
            ))
    return sorted(trades, key=lambda trade: (trade.entry_at, trade.setup_id))


def metrics(rows: list[Trade], baseline_count: int) -> dict[str, Any]:
    pnl = sum(row.pnl for row in rows)
    wins = sum(row.pnl > 0 for row in rows)
    gross_win = sum(max(0.0, row.pnl) for row in rows)
    gross_loss = -sum(min(0.0, row.pnl) for row in rows)
    running = peak = drawdown = 0.0
    for row in sorted(rows, key=lambda trade: (trade.exit_at, trade.setup_id)):
        running += row.pnl
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)

    points: list[tuple[datetime, int]] = []
    for row in rows:
        points.append((row.entry_at, 1))
        points.append((row.exit_at, -1))
    active = peak_active = 0
    for _, delta in sorted(points, key=lambda point: (point[0], point[1])):
        active += delta
        peak_active = max(peak_active, active)

    # Fixed five-slot, $1,000-per-trade admission simulation.  This measures
    # opportunity cost consistently; it is not a broker fill model.
    active_exits: list[datetime] = []
    constrained: list[Trade] = []
    for row in sorted(rows, key=lambda trade: (trade.entry_at, trade.setup_id)):
        active_exits = [stamp for stamp in active_exits if stamp > row.entry_at]
        if len(active_exits) >= 5:
            continue
        active_exits.append(row.exit_at)
        constrained.append(row)

    return {
        "trades": len(rows),
        "retained_pct": 100.0 * len(rows) / baseline_count if baseline_count else 0.0,
        "reduction_pct": 100.0 * (1.0 - len(rows) / baseline_count) if baseline_count else 0.0,
        "pnl": pnl,
        "avg_pnl": pnl / len(rows) if rows else 0.0,
        "win_rate": 100.0 * wins / len(rows) if rows else 0.0,
        # JSON has no portable representation for infinity.
        "profit_factor": gross_win / gross_loss if gross_loss else None,
        "max_drawdown": drawdown,
        "peak_active": peak_active,
        "five_slot_trades": len(constrained),
        "five_slot_pnl": sum(row.pnl for row in constrained),
        "positive_days": sum(
            sum(row.pnl for row in rows if row.day == day) > 0
            for day in sorted({row.day for row in rows})
        ),
        "by_day": {
            day: {
                "trades": sum(row.day == day for row in rows),
                "pnl": sum(row.pnl for row in rows if row.day == day),
            }
            for day in sorted({row.day for row in rows})
        },
    }


def numeric_rules(train: list[Trade]) -> list[Rule]:
    values_by_field: dict[str, list[float]] = defaultdict(list)
    for trade in train:
        for field, value in trade.features.items():
            if finite_number(value):
                values_by_field[field].append(float(value))
    rules: list[Rule] = []
    for field, values in values_by_field.items():
        if len(values) < 100 or len(set(values)) < 10:
            continue
        for fraction in KEEP_FRACTIONS:
            for direction, q in (("HIGH", 1.0 - fraction), ("LOW", fraction)):
                threshold = quantile(values, q)
                if direction == "HIGH":
                    predicate = lambda trade, f=field, t=threshold: (
                        finite_number(trade.features.get(f))
                        and float(trade.features[f]) >= t
                    )
                else:
                    predicate = lambda trade, f=field, t=threshold: (
                        finite_number(trade.features.get(f))
                        and float(trade.features[f]) <= t
                    )
                rules.append(Rule(
                    f"numeric:{field}:{direction}:{fraction:.2f}",
                    f"{field} {direction} {threshold:.8g} (train keep~{fraction:.0%})",
                    predicate,
                ))
    return rules


def categorical_rules(train: list[Trade]) -> list[Rule]:
    counts: dict[str, dict[Any, int]] = defaultdict(lambda: defaultdict(int))
    for trade in train:
        for field, value in trade.features.items():
            if isinstance(value, (str, bool)):
                counts[field][value] += 1
    rules: list[Rule] = []
    minimum = max(30, int(len(train) * 0.03))
    for field, options in counts.items():
        for value, count in options.items():
            if count < minimum or count >= len(train) * 0.97:
                continue
            rules.append(Rule(
                f"categorical:{field}:{value}",
                f"{field} == {value!r}",
                lambda trade, f=field, v=value: trade.features.get(f) == v,
            ))
    return rules


def apply_cooldown(rows: list[Trade], minutes: int) -> list[Trade]:
    selected: list[Trade] = []
    last: dict[str, datetime] = {}
    seconds = minutes * 60
    for row in sorted(rows, key=lambda trade: (trade.entry_at, trade.setup_id)):
        previous = last.get(row.symbol)
        if previous is not None and (row.entry_at - previous).total_seconds() < seconds:
            continue
        selected.append(row)
        last[row.symbol] = row.entry_at
    return selected


def apply_top_n(rows: list[Trade], field: str, direction: str, count: int) -> list[Trade]:
    groups: dict[tuple[str, str], list[Trade]] = defaultdict(list)
    for row in rows:
        minute = row.entry_at.replace(second=0, microsecond=0).isoformat()
        groups[(row.strategy, minute)].append(row)
    selected: list[Trade] = []
    reverse = direction == "HIGH"
    for group in groups.values():
        available = [row for row in group if finite_number(row.features.get(field))]
        available.sort(key=lambda row: float(row.features[field]), reverse=reverse)
        selected.extend(available[:count])
    return sorted(selected, key=lambda trade: (trade.entry_at, trade.setup_id))


def score_candidate(train_metrics: dict[str, Any], valid_metrics: dict[str, Any]) -> tuple:
    return (
        train_metrics["pnl"] > 0,
        valid_metrics["pnl"] > 0,
        valid_metrics["positive_days"],
        valid_metrics["five_slot_pnl"],
        valid_metrics["avg_pnl"],
        train_metrics["positive_days"],
        train_metrics["avg_pnl"],
        valid_metrics["reduction_pct"],
    )


def analyze_strategy(
    strategy: str,
    rows: list[Trade],
    train_days: set[str],
    valid_days: set[str],
) -> dict[str, Any]:
    train = [row for row in rows if row.day in train_days]
    valid = [row for row in rows if row.day in valid_days]
    baseline_train = metrics(train, len(train))
    baseline_valid = metrics(valid, len(valid))

    candidates: list[dict[str, Any]] = []
    base_rules = numeric_rules(train) + categorical_rules(train)
    for rule in base_rules:
        selected_train = [row for row in train if rule.predicate(row)]
        selected_valid = [row for row in valid if rule.predicate(row)]
        if len(selected_train) < 30 or len(selected_valid) < 10:
            continue
        tm = metrics(selected_train, len(train))
        vm = metrics(selected_valid, len(valid))
        candidates.append({
            "kind": "single",
            "name": rule.name,
            "description": rule.description,
            "train": tm,
            "valid": vm,
            "rule": rule,
        })

    for minutes in COOLDOWN_MINUTES:
        selected_train = apply_cooldown(train, minutes)
        selected_valid = apply_cooldown(valid, minutes)
        candidates.append({
            "kind": "cooldown",
            "name": f"cooldown:{minutes}",
            "description": f"one {strategy} entry per symbol per {minutes} minutes",
            "train": metrics(selected_train, len(train)),
            "valid": metrics(selected_valid, len(valid)),
        })

    # Rank candidates use every varying numeric entry feature.  The same field
    # and direction are applied independently within each signal minute.
    numeric_fields = sorted({
        field
        for row in train
        for field, value in row.features.items()
        if finite_number(value)
    })
    for field in numeric_fields:
        if len({row.features.get(field) for row in train if finite_number(row.features.get(field))}) < 10:
            continue
        for direction in ("HIGH", "LOW"):
            for count in TOP_NS:
                selected_train = apply_top_n(train, field, direction, count)
                selected_valid = apply_top_n(valid, field, direction, count)
                if len(selected_train) < 30 or len(selected_valid) < 10:
                    continue
                candidates.append({
                    "kind": "top_n",
                    "name": f"top_n:{field}:{direction}:{count}",
                    "description": f"top {count}/minute by {field} ({direction})",
                    "train": metrics(selected_train, len(train)),
                    "valid": metrics(selected_valid, len(valid)),
                })

    # Test only a bounded set of promising simple-rule interactions to avoid a
    # combinatorial search.  Rules must first improve average train P&L.
    promising = [candidate for candidate in candidates if (
        candidate["kind"] == "single"
        and candidate["train"]["avg_pnl"] > baseline_train["avg_pnl"]
        and candidate["train"]["reduction_pct"] >= 30
    )]
    promising.sort(key=lambda candidate: candidate["train"]["avg_pnl"], reverse=True)
    promising = promising[:12]
    for index, left in enumerate(promising):
        for right in promising[index + 1:]:
            left_rule = left["rule"]
            right_rule = right["rule"]
            selected_train = [
                row for row in train
                if left_rule.predicate(row) and right_rule.predicate(row)
            ]
            selected_valid = [
                row for row in valid
                if left_rule.predicate(row) and right_rule.predicate(row)
            ]
            if len(selected_train) < 30 or len(selected_valid) < 10:
                continue
            candidates.append({
                "kind": "pair",
                "name": f"pair:{left['name']}+{right['name']}",
                "description": f"({left['description']}) AND ({right['description']})",
                "train": metrics(selected_train, len(train)),
                "valid": metrics(selected_valid, len(valid)),
            })

    for candidate in candidates:
        candidate["score"] = score_candidate(candidate["train"], candidate["valid"])
        candidate.pop("rule", None)
    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)

    # Capacity/profit Pareto set on validation: no retained candidate may have
    # both more trades and lower P&L than another candidate.
    pareto = []
    for candidate in candidates:
        vm = candidate["valid"]
        dominated = any(
            other["valid"]["trades"] <= vm["trades"]
            and other["valid"]["pnl"] >= vm["pnl"]
            and (
                other["valid"]["trades"] < vm["trades"]
                or other["valid"]["pnl"] > vm["pnl"]
            )
            for other in candidates
        )
        if not dominated:
            pareto.append(candidate)
    pareto.sort(key=lambda candidate: candidate["valid"]["trades"])

    return {
        "strategy": strategy,
        "baseline_train": baseline_train,
        "baseline_valid": baseline_valid,
        "top_candidates": candidates[:25],
        "pareto": pareto[:40],
    }


def printable(candidate: dict[str, Any]) -> str:
    tm, vm = candidate["train"], candidate["valid"]
    return (
        f"{candidate['kind']:8s} "
        f"TR n={tm['trades']:5d} red={tm['reduction_pct']:5.1f}% "
        f"pnl={tm['pnl']:+9.2f} avg={tm['avg_pnl']:+7.3f} "
        f"VA n={vm['trades']:5d} red={vm['reduction_pct']:5.1f}% "
        f"pnl={vm['pnl']:+9.2f} avg={vm['avg_pnl']:+7.3f} "
        f"5slot={vm['five_slot_pnl']:+8.2f} | {candidate['description']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/data"))
    parser.add_argument("--strategies", default=DEFAULT_STRATEGIES)
    parser.add_argument("--train-days", default="2026-08-11,2026-08-12,2026-08-13")
    parser.add_argument("--valid-days", default="2026-08-14")
    parser.add_argument("--output", type=Path, default=Path("/data/admission_analysis.json"))
    args = parser.parse_args()

    strategies = {value.strip() for value in args.strategies.split(",") if value.strip()}
    train_days = {value.strip() for value in args.train_days.split(",") if value.strip()}
    valid_days = {value.strip() for value in args.valid_days.split(",") if value.strip()}
    days = train_days | valid_days
    if train_days & valid_days:
        raise SystemExit("training and validation days must be disjoint")

    reports = []
    signal_total = 0
    trade_total = 0
    for strategy in sorted(strategies):
        # Process one strategy at a time.  A full ten-strategy feature map can
        # consume several GB because every Python scalar/dict has substantial
        # overhead.  This deliberately trades additional archive scans for a
        # much smaller and predictable resident-memory footprint.
        print(f"\nLoading SIGNAL events for {strategy}...", flush=True)
        signals = load_signals(args.root, {strategy}, days)
        print(f"Loaded {len(signals)} unique {strategy} signals; joining outcomes...", flush=True)
        rows = load_trades(args.root, signals)
        print(f"Joined {len(rows)} completed {strategy} trades", flush=True)
        signal_total += len(signals)
        trade_total += len(rows)
        report = analyze_strategy(strategy, rows, train_days, valid_days)
        reports.append(report)
        bt, bv = report["baseline_train"], report["baseline_valid"]
        print("\n" + "=" * 120)
        print(
            f"{strategy} BASELINE | "
            f"train n={bt['trades']} pnl={bt['pnl']:+.2f} avg={bt['avg_pnl']:+.3f} "
            f"| valid n={bv['trades']} pnl={bv['pnl']:+.2f} avg={bv['avg_pnl']:+.3f}"
        )
        print("TOP CANDIDATES")
        for candidate in report["top_candidates"][:12]:
            print(printable(candidate))
        print("VALIDATION PARETO FRONT")
        for candidate in report["pareto"][:12]:
            print(printable(candidate))
        del rows, signals
        gc.collect()

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "root": str(args.root),
        "train_days": sorted(train_days),
        "valid_days": sorted(valid_days),
        "signals": signal_total,
        "trades": trade_total,
        "reports": reports,
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    print(f"\nWROTE {args.output}")


if __name__ == "__main__":
    main()
