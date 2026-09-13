#!/usr/bin/env python3
"""
Module Factory v1.

Automatically generates and evaluates cascade-family candidates against
multiple independent market tapes.

Research only:
- does not import the live strategy registry
- does not modify strategy files
- cannot place orders
- cannot promote anything to live trading

A candidate is rewarded for working across independent days, not for having
the best pooled historical result.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from research_tools.cascade_reversal_study import load_minute_bars
from research_tools.module_factory.fast_cascade import (
    extract_observations,
    filter_observations,
)


@dataclass(frozen=True)
class Candidate:
    family: str
    direction: str
    window_minutes: int
    min_drop_pct: float
    min_down_minutes: int
    near_low_bps: float
    max_single_minute_drop_pct: float
    max_spy_drop_pct: float
    cooldown_minutes: int
    horizon: int

    @property
    def candidate_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        digest = hashlib.sha1(payload.encode()).hexdigest()[:10].upper()
        return f"MF-{digest}"


@dataclass
class DayResult:
    tape: str
    events: int
    mean_net_pct: float | None
    median_net_pct: float | None
    win_rate_pct: float | None
    worst_net_pct: float | None
    best_net_pct: float | None


@dataclass
class CandidateResult:
    candidate: Candidate
    days: list[DayResult]
    total_events: int
    profitable_days: int
    tested_days: int
    worst_day_mean_pct: float | None
    average_day_mean_pct: float | None
    score: float | None
    status: str
    rejection_reason: str | None


def generate_candidates() -> list[Candidate]:
    """
    Small, intentionally predeclared v1 search space.

    Later factory versions can add families and mutations.  We start narrow
    so the infrastructure is tested before expanding the hypothesis space.
    """
    candidates = []

    for (
        direction,
        window,
        drop,
        downs,
        near_low,
        spy_drop,
        horizon,
    ) in itertools.product(
        ("long", "short"),
        (8, 10, 12),
        (0.75, 1.00, 1.25, 1.50),
        (5, 6, 7, 8),
        (10.0, 20.0),
        (0.25, 0.50),
        (10, 20),
    ):
        if downs >= window:
            continue

        candidates.append(
            Candidate(
                family="cascade",
                direction=direction,
                window_minutes=window,
                min_drop_pct=drop,
                min_down_minutes=downs,
                near_low_bps=near_low,
                max_single_minute_drop_pct=0.50,
                max_spy_drop_pct=spy_drop,
                cooldown_minutes=20,
                horizon=horizon,
            )
        )

    return candidates


def _net_returns(events, candidate: Candidate, cost_bps: float) -> list[float]:
    values = []

    for event in events:
        if candidate.horizon not in event.returns:
            continue

        # Detector was deliberately called with zero cost.
        raw_long = event.returns[candidate.horizon]

        if candidate.direction == "long":
            gross = raw_long
        elif candidate.direction == "short":
            gross = -raw_long
        else:
            raise ValueError(candidate.direction)

        values.append(gross - cost_bps / 100.0)

    return values


def evaluate_candidate(
    candidate: Candidate,
    caches: dict[str, dict[int, list]],
    *,
    cost_bps: float,
    min_events_per_day: int,
    min_tested_days: int,
) -> CandidateResult:

    day_results = []

    for tape_name, window_caches in caches.items():
        observations = window_caches[candidate.window_minutes]

        events = filter_observations(
            observations,
            min_drop_pct=candidate.min_drop_pct,
            min_down_minutes=candidate.min_down_minutes,
            near_low_bps=candidate.near_low_bps,
            max_single_minute_drop_pct=candidate.max_single_minute_drop_pct,
            max_spy_drop_pct=candidate.max_spy_drop_pct,
            cooldown_minutes=candidate.cooldown_minutes,
        )

        values = _net_returns(events, candidate, cost_bps)

        if values:
            day_results.append(
                DayResult(
                    tape=tape_name,
                    events=len(values),
                    mean_net_pct=mean(values),
                    median_net_pct=median(values),
                    win_rate_pct=100.0 * sum(x > 0 for x in values) / len(values),
                    worst_net_pct=min(values),
                    best_net_pct=max(values),
                )
            )
        else:
            day_results.append(
                DayResult(
                    tape=tape_name,
                    events=0,
                    mean_net_pct=None,
                    median_net_pct=None,
                    win_rate_pct=None,
                    worst_net_pct=None,
                    best_net_pct=None,
                )
            )

    eligible_days = [
        day
        for day in day_results
        if day.events >= min_events_per_day
        and day.mean_net_pct is not None
    ]

    means = [day.mean_net_pct for day in eligible_days]
    tested_days = len(eligible_days)
    profitable_days = sum(x > 0 for x in means)

    worst_day = min(means) if means else None
    average_day = mean(means) if means else None
    total_events = sum(day.events for day in eligible_days)

    rejection = None

    if tested_days < min_tested_days:
        rejection = "insufficient_independent_days"
    elif profitable_days != tested_days:
        rejection = "negative_day"
    elif worst_day is None or worst_day <= 0:
        rejection = "nonpositive_worst_day"
    elif total_events < min_events_per_day * min_tested_days:
        rejection = "insufficient_events"

    status = "REJECTED" if rejection else "HISTORICAL_PASS"

    score = (
        0.75 * worst_day + 0.25 * average_day
        if worst_day is not None and average_day is not None
        else None
    )

    return CandidateResult(
        candidate=candidate,
        days=day_results,
        total_events=total_events,
        profitable_days=profitable_days,
        tested_days=tested_days,
        worst_day_mean_pct=worst_day,
        average_day_mean_pct=average_day,
        score=score,
        status=status,
        rejection_reason=rejection,
    )


def append_ledger(path: Path, results: Iterable[CandidateResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    with path.open("a", encoding="utf-8") as handle:
        for result in results:
            record = {
                "factory_version": 1,
                "evaluated_at_utc": now,
                "candidate": asdict(result.candidate),
                "candidate_id": result.candidate.candidate_id,
                "days": [asdict(day) for day in result.days],
                "total_events": result.total_events,
                "profitable_days": result.profitable_days,
                "tested_days": result.tested_days,
                "worst_day_mean_pct": result.worst_day_mean_pct,
                "average_day_mean_pct": result.average_day_mean_pct,
                "score": result.score,
                "status": result.status,
                "rejection_reason": result.rejection_reason,
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def print_report(results: list[CandidateResult], top: int) -> None:
    ranked = sorted(
        results,
        key=lambda r: (
            r.status == "HISTORICAL_PASS",
            r.score if r.score is not None else -math.inf,
            r.total_events,
        ),
        reverse=True,
    )

    passed = [r for r in ranked if r.status == "HISTORICAL_PASS"]

    print()
    print("MODULE FACTORY v1")
    print("=" * 100)
    print(f"Candidates evaluated: {len(results)}")
    print(f"Historical passes:    {len(passed)}")
    print(f"Rejected:             {len(results) - len(passed)}")
    print()
    print(
        f"{'ID':<14} {'DIR':<5} {'WIN':>3} {'DROP':>5} {'DOWN':>4} "
        f"{'LOW':>5} {'SPY':>5} {'H':>3} {'EVENTS':>7} "
        f"{'WORST%':>8} {'AVG%':>8} {'SCORE':>8} {'STATUS'}"
    )
    print("-" * 100)

    for result in ranked[:top]:
        c = result.candidate

        def fmt(value):
            return "      NA" if value is None else f"{value:+8.3f}"

        print(
            f"{c.candidate_id:<14} {c.direction:<5} "
            f"{c.window_minutes:>3} {c.min_drop_pct:>5.2f} "
            f"{c.min_down_minutes:>4} {c.near_low_bps:>5.0f} "
            f"{c.max_spy_drop_pct:>5.2f} {c.horizon:>3} "
            f"{result.total_events:>7} "
            f"{fmt(result.worst_day_mean_pct)} "
            f"{fmt(result.average_day_mean_pct)} "
            f"{fmt(result.score)} {result.status}"
        )

    if passed:
        print()
        print("HISTORICAL_PASS means candidate for further validation only.")
        print("It does NOT authorize shadow, paper, or live trading.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tape",
        action="append",
        required=True,
        help="Minute quote tape. Repeat for independent trading days.",
    )
    parser.add_argument(
        "--ledger",
        default="research_data/module_factory_ledger.jsonl",
    )
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--min-events-per-day", type=int, default=20)
    parser.add_argument("--min-tested-days", type=int, default=2)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional candidate limit for smoke tests.",
    )
    args = parser.parse_args()

    if len(args.tape) < args.min_tested_days:
        raise SystemExit(
            f"Need at least {args.min_tested_days} independent tapes."
        )

    print("Loading independent tapes once...")
    tapes = {}

    for path in args.tape:
        bars = load_minute_bars([path])
        tapes[path] = bars
        print(
            f"Loaded {path}: {len(bars)} symbols, "
            f"{sum(len(x) for x in bars.values())} minute bars"
        )

    candidates = generate_candidates()
    if args.limit is not None:
        candidates = candidates[: args.limit]

    windows = sorted({candidate.window_minutes for candidate in candidates})
    horizons = tuple(sorted({candidate.horizon for candidate in candidates}))

    print(
        f"\nBuilding reusable feature caches for "
        f"{len(tapes)} tapes x {len(windows)} windows..."
    )

    caches = {}

    for tape_name, bars in tapes.items():
        caches[tape_name] = {}
        for window in windows:
            observations = extract_observations(
                bars,
                window_minutes=window,
                horizons=horizons,
            )
            caches[tape_name][window] = observations
            print(
                f"  {Path(tape_name).name}: window={window} "
                f"observations={len(observations)}"
            )

    print(f"\nEvaluating {len(candidates)} candidates from caches...")

    results = []

    for number, candidate in enumerate(candidates, 1):
        result = evaluate_candidate(
            candidate,
            caches,
            cost_bps=args.cost_bps,
            min_events_per_day=args.min_events_per_day,
            min_tested_days=args.min_tested_days,
        )
        results.append(result)

        if number % 100 == 0:
            print(f"  evaluated {number}/{len(candidates)}", flush=True)

    print_report(results, args.top)
    append_ledger(Path(args.ledger), results)
    print(f"\nLedger appended: {args.ledger}")


if __name__ == "__main__":
    main()
