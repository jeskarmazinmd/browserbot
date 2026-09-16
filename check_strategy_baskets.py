"""Exploratory shared-capital basket check for browserbot research data.

This is hypothesis-generation only. It reuses research_lab.capital.simulate_day,
which previously matched production paper accounting. It does not establish
market executability or justify live capital.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
from itertools import combinations
from pathlib import Path

from research_lab.capital import NY, simulate_day
from research_lab.discovery import build_report
from research_lab.evidence import build_evidence


DEFAULT_CANDIDATES = (
    "C2", "C1", "G", "P", "C1F1", "EMA1", "J2", "L", "H", "Q",
    "GT1", "TD1", "M", "J6", "C3", "O", "EMA3", "AV1",
)


def valid_trade(t):
    return (
        t.entered
        and t.entry_price is not None
        and t.stop_price is not None
        and t.exit_price is not None
        and t.exit_time is not None
        and t.entry_price > 0
        and t.exit_price > 0
        and t.exit_time >= t.entry_time
    )


def group_trades(evidence):
    out = defaultdict(lambda: defaultdict(list))
    for t in evidence.trades:
        if not valid_trade(t):
            continue
        day = t.entry_time.astimezone(NY).date().isoformat()
        out[t.strategy_id][day].append(t)
    return out


def ordered_for_mode(trades, members, mode):
    if mode == "RECORDED":
        return list(trades)

    ids = sorted(members, reverse=(mode == "Z_TO_A"))
    priority = {sid: i for i, sid in enumerate(ids)}
    ordered = sorted(
        trades,
        key=lambda t: (
            t.entry_time,
            priority.get(t.strategy_id, len(priority)),
            t.setup_id,
        ),
    )
    return [replace(t, entry_sequence=None) for t in ordered]


def run_portfolio(grouped, members, days, mode="RECORDED"):
    equity = 5000.0
    peak = equity
    max_dd = 0.0
    taken = 0
    signals = 0
    daily = []

    for day in sorted(days):
        trades = []
        for sid in members:
            trades.extend(grouped[sid].get(day, ()))
        trades = ordered_for_mode(trades, members, mode)
        result = simulate_day(trades, starting_cash=equity)
        equity = result.end_equity
        taken += result.taken
        signals += result.signals
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        daily.append((day, equity))

    return {
        "end": equity,
        "return_pct": (equity / 5000.0 - 1.0) * 100.0,
        "max_daily_close_dd_pct": max_dd,
        "taken": taken,
        "signals": signals,
        "daily": daily,
    }


def overlap_pct(grouped, members, days):
    groups = defaultdict(list)
    total = 0
    for sid in members:
        for day in days:
            for t in grouped[sid].get(day, ()):
                groups[(t.symbol, t.signal_time)].append(t)
                total += 1
    redundant = sum(max(0, len(v) - 1) for v in groups.values())
    return (100.0 * redundant / total) if total else 0.0


def evaluate_combo(grouped, members, min_days):
    day_sets = [set(grouped[sid]) for sid in members]
    days = set.intersection(*day_sets) if day_sets else set()
    if len(days) < min_days:
        return None

    singles = {
        sid: run_portfolio(grouped, (sid,), days)
        for sid in members
    }
    best_sid, best = max(
        singles.items(), key=lambda kv: kv[1]["return_pct"]
    )

    modes = {
        mode: run_portfolio(grouped, members, days, mode)
        for mode in ("RECORDED", "A_TO_Z", "Z_TO_A")
    }
    returns = [x["return_pct"] for x in modes.values()]
    robust_return = min(returns)
    best_single = best["return_pct"]

    return {
        "members": members,
        "days": tuple(sorted(days)),
        "best_single_sid": best_sid,
        "best_single_return": best_single,
        "recorded_return": modes["RECORDED"]["return_pct"],
        "robust_return": robust_return,
        "robust_delta": robust_return - best_single,
        "order_spread": max(returns) - min(returns),
        "overlap_pct": overlap_pct(grouped, members, days),
        "dd": modes["RECORDED"]["max_daily_close_dd_pct"],
        "taken": modes["RECORDED"]["taken"],
        "signals": modes["RECORDED"]["signals"],
    }


def print_rows(title, rows, limit):
    print(f"\n{title}")
    print(
        f"{'BASKET':29} {'D':>2} {'REC%':>8} {'ROB%':>8} {'BEST':>7} "
        f"{'DELTA':>8} {'OVLP':>7} {'ORD':>7} {'DD':>7} {'TAKEN':>6}"
    )
    for row in rows[:limit]:
        name = "+".join(row["members"])
        print(
            f"{name[:29]:29} {len(row['days']):2d} "
            f"{row['recorded_return']:+7.2f}% "
            f"{row['robust_return']:+7.2f}% "
            f"{row['best_single_sid']:>7} "
            f"{row['robust_delta']:+7.2f} "
            f"{row['overlap_pct']:6.1f}% "
            f"{row['order_spread']:6.2f} "
            f"{row['dd']:6.2f}% "
            f"{row['taken']:6d}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--data-root", default="research_data")
    ap.add_argument("--min-days", type=int, default=2)
    ap.add_argument("--max-size", type=int, default=4)
    ap.add_argument("--show", type=int, default=15)
    ap.add_argument("--max-records-per-source", type=int, default=None)
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    data = Path(args.data_root).resolve()
    print("BUILDING EVIDENCE...")
    report = build_report(repo, data, "sample", 2000)
    evidence = build_evidence(
        report.sources,
        max_records_per_source=args.max_records_per_source,
    )
    grouped = group_trades(evidence)

    available = [sid for sid in DEFAULT_CANDIDATES if sid in grouped]
    print("trades:", len(evidence.trades))
    print("candidates:", ",".join(available))

    print("\nSINGLES (own available days; descriptive only)")
    singles = []
    for sid in available:
        days = set(grouped[sid])
        if len(days) < args.min_days:
            continue
        r = run_portfolio(grouped, (sid,), days)
        singles.append((r["return_pct"], sid, len(days), r["taken"], r["signals"]))
    for ret, sid, ndays, taken, signals in sorted(singles, reverse=True):
        print(
            f"{sid:8} days={ndays:2d} return={ret:+7.2f}% "
            f"taken={taken:4d}/{signals:4d}"
        )

    rows = []
    for size in range(2, min(args.max_size, len(available)) + 1):
        for members in combinations(available, size):
            item = evaluate_combo(grouped, members, args.min_days)
            if item is not None:
                rows.append(item)

    rows.sort(key=lambda x: (x["robust_delta"], x["robust_return"]), reverse=True)
    print_rows("TOP BASKETS VS THEIR BEST MEMBER ON THE SAME DAYS", rows, args.show)

    diverse = [x for x in rows if x["overlap_pct"] <= 20.0]
    diverse.sort(
        key=lambda x: (x["robust_delta"], x["robust_return"]),
        reverse=True,
    )
    print_rows("TOP LOWER-OVERLAP BASKETS (<=20% redundant signals)", diverse, args.show)

    winners = [x for x in rows if x["robust_delta"] > 0]
    print("\nSUMMARY")
    print("tested_baskets:", len(rows))
    print("robustly_beat_best_member:", len(winners))
    if winners:
        best = winners[0]
        print("best_candidate:", "+".join(best["members"]))
        print("common_days:", ",".join(best["days"]))
        print("robust_delta_pp:", round(best["robust_delta"], 3))
        print("overlap_pct:", round(best["overlap_pct"], 2))
    print(
        "\nCAUTION: historical paper-accounting evidence only; not proof of "
        "executability or prospective profitability."
    )


if __name__ == "__main__":
    main()
