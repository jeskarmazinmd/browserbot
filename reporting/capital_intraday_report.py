"""Print a read-only $5,000 hypothetical-close report for the main modules."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import csv
import gzip
import json
from pathlib import Path
import zlib
from zoneinfo import ZoneInfo

from reporting.all_engine_performance import load_market_marks
from reporting.capital_performance import simulate_day
from reporting.capital_performance_worker import compact_exit, load_archive, market_day


HISTORY_NAME = "capital_bidask_daily_history.json"
MAX_MARK_AGE_SECONDS = 180.0


def load_snapshot_rows(ledger: Path, marks: dict, day: str, as_of: datetime):
    """Return completed rows plus synthetic exits for positions open at *as_of*."""
    sequence_by_setup = {}
    active = {}
    completed = []
    next_sequence = 0

    try:
        handle = ledger.open(errors="replace")
    except OSError:
        return [], 0, {}

    with handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(row, dict):
                continue

            setup = str(row.get("setup_id") or "")
            event = row.get("event_type")
            if not setup:
                continue

            if event == "PAPER_ENTRY":
                if setup not in sequence_by_setup:
                    sequence_by_setup[setup] = next_sequence
                    next_sequence += 1
                active[setup] = row
            elif event == "PAPER_EXIT":
                entry = active.pop(setup, None)
                sequence = sequence_by_setup.get(setup)
                if entry is not None and sequence is not None and market_day(row) == day:
                    completed.append(compact_exit(row, sequence))

    rows = list(completed)
    unpriced = 0
    for setup, entry in active.items():
        if market_day(entry) != day:
            continue
        try:
            price = float(marks["main_last"][str(entry["symbol"])])
        except (KeyError, TypeError, ValueError):
            unpriced += 1
            continue
        if price <= 0:
            unpriced += 1
            continue

        synthetic = dict(entry)
        synthetic.update({
            "exit_timestamp": as_of.isoformat(),
            "exit_price": price,
            "exit_reason": "HYPOTHETICAL_CLOSE_AT_CURRENT_LAST",
        })
        rows.append(compact_exit(synthetic, sequence_by_setup[setup]))
        rows[-1]["hypothetical_open"] = True

    return rows, unpriced, sequence_by_setup


def load_current_bids(root: Path, day: str, as_of: datetime) -> dict[str, float]:
    """Load the newest rich-archive bid at or before *as_of* for each symbol."""
    result = {}
    path = root / "research_market" / f"minute_market_quotes_{day.replace('-', '')}.csv.gz"
    try:
        handle = gzip.open(path, "rt", newline="", errors="replace")
    except OSError:
        return result
    with handle:
        try:
            for row in csv.DictReader(handle):
                try:
                    observed = datetime.fromisoformat(
                        str(row.get("observed_at_utc") or row.get("market_minute_utc"))
                        .replace("Z", "+00:00")
                    )
                    bid = float(row["bid"])
                    symbol = str(row["symbol"]).upper()
                except (KeyError, TypeError, ValueError):
                    continue
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                age = (as_of - observed.astimezone(timezone.utc)).total_seconds()
                if 0 <= age <= MAX_MARK_AGE_SECONDS and bid > 0 and symbol:
                    result[symbol] = bid
        except (EOFError, OSError, zlib.error):
            # The collector appends gzip members while this report may be
            # reading. Preserve every complete quote row read before a partial
            # or damaged tail rather than failing the entire snapshot.
            pass
    return result


def persisted_bids(marks: dict) -> dict[str, float]:
    result = {}
    for symbol, quote in marks.get("equity", {}).items():
        try:
            bid = float(quote["bid"])
        except (KeyError, TypeError, ValueError):
            continue
        if bid > 0:
            result[str(symbol).upper()] = bid
    return result


def load_bidask_rows(
    ledger: Path,
    bids: dict[str, float],
    day: str,
    as_of: datetime,
    sequence_by_setup: dict[str, int],
):
    """Load completed B/A twins and mark their open positions at current bid."""
    entries = {}
    exits = {}
    try:
        handle = ledger.open(errors="replace")
    except OSError:
        return [], 0
    with handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(row, dict):
                continue
            setup = str(row.get("parent_setup_id") or row.get("setup_id") or "")
            if not setup:
                continue
            event = str(row.get("event_type") or "").upper()
            if event == "BA_REPRICE_ENTRY":
                entries[setup] = row
            elif event == "BA_REPRICE_EXIT":
                exits[setup] = row

    rows = []
    unpriced = 0
    for setup, entry in entries.items():
        sequence = sequence_by_setup.get(setup)
        if sequence is None or market_day(entry) != day:
            continue
        exit_row = exits.get(setup)
        if exit_row is not None:
            rows.append(compact_exit(exit_row, sequence))
            continue
        try:
            bid = float(bids[str(entry["symbol"]).upper()])
        except (KeyError, TypeError, ValueError):
            unpriced += 1
            continue
        synthetic = dict(entry)
        synthetic.update({
            "exit_timestamp": as_of.isoformat(),
            "exit_price": bid,
            "exit_bid": bid,
            "exit_reason": "HYPOTHETICAL_CLOSE_AT_CURRENT_BID",
        })
        rows.append(compact_exit(synthetic, sequence))
        rows[-1]["hypothetical_open"] = True
    return rows, unpriced


def _group(rows):
    grouped = defaultdict(list)
    for row in rows:
        strategy = str(row.get("strategy_id") or "")
        if strategy:
            grouped[strategy].append(row)
    return grouped


def summarize_paired(parent_rows, ba_rows):
    parent_by_setup = {str(row.get("setup_id") or ""): row for row in parent_rows}
    ba_by_setup = {str(row.get("setup_id") or ""): row for row in ba_rows}
    strategies = sorted({str(row.get("strategy_id") or "") for row in parent_rows})
    result = {}
    for strategy in strategies:
        if not strategy:
            continue
        full = [row for row in parent_rows if row.get("strategy_id") == strategy]
        paired_ids = {
            setup for setup, row in ba_by_setup.items()
            if row.get("strategy_id") == strategy and setup in parent_by_setup
        }
        paired_last = [parent_by_setup[setup] for setup in paired_ids]
        paired_ba = [ba_by_setup[setup] for setup in paired_ids]
        realized_ba = [row for row in paired_ba if not row.get("hypothetical_open")]
        full_result = simulate_day(full)
        last_result = simulate_day(paired_last)
        ba_result = simulate_day(paired_ba)
        realized_result = simulate_day(realized_ba)
        result[strategy] = {
            "full_last": full_result,
            "paired_last": last_result,
            "paired_ba": ba_result,
            "realized_ba": realized_result,
            "coverage_pct": len(paired_ids) / len(full) * 100.0 if full else 0.0,
            "open_pairs": sum(bool(row.get("hypothetical_open")) for row in paired_ba),
        }
    return result


def render(parent_rows, ba_rows, day: str, as_of: datetime, parent_unpriced: int, ba_unpriced: int) -> str:
    summaries = summarize_paired(parent_rows, ba_rows)

    ranked = sorted(
        summaries.items(),
        key=lambda item: item[1]["paired_ba"]["return_pct"],
        reverse=True,
    )
    lines = [
        f"$5,000 LAST vs REALISTIC BID/ASK HYPOTHETICAL CLOSE — {day}",
        f"As of {as_of.astimezone(timezone.utc).isoformat()} | open LAST@latest trade; B/A longs@latest bid",
        "1% equity risk/trade | 20% maximum position | whole shares",
        "Read-only snapshot; no positions or finalized history were changed",
        "",
        (
            f"{'Rank':>4} {'Module':<20} {'FullLAST':>9} {'PairLAST':>9} "
            f"{'Pair B/A':>9} {'Real B/A':>9} {'Drag':>9} {'Open':>6} {'Coverage':>9}"
        ),
        "-" * 112,
    ]
    for rank, (strategy, row) in enumerate(ranked, 1):
        full = row["full_last"]["return_pct"]
        paired_last = row["paired_last"]["return_pct"]
        ba = row["paired_ba"]["return_pct"]
        realized = row["realized_ba"]["return_pct"]
        lines.append(
            f"{rank:>4} {strategy:<20} {full:>+8.2f}% {paired_last:>+8.2f}% "
            f"{ba:>+8.2f}% {realized:>+8.2f}% {ba-paired_last:>+8.2f}% "
            f"{row['open_pairs']:>6} {row['coverage_pct']:>8.1f}%"
        )
    if not ranked:
        lines.append("No priced trades found for this market day.")
    if parent_unpriced or ba_unpriced:
        lines.extend([
            "",
            f"Unpriced open positions excluded: LAST={parent_unpriced} | B/A={ba_unpriced}",
        ])
    lines.append("Drag compares identical setup IDs only: paired B/A minus paired LAST.")
    lines.append(f"Open B/A marks older than {int(MAX_MARK_AGE_SECONDS)}s are excluded; Real B/A contains closed trades only.")
    return "\n".join(lines) + "\n"


def load_daily_history(root: Path) -> dict:
    try:
        value = json.loads((root / HISTORY_NAME).read_text())
        if isinstance(value, dict) and isinstance(value.get("days"), dict):
            return value
    except (OSError, TypeError, ValueError):
        pass
    return {"version": 1, "days": {}}


def save_finalized_day(root: Path, day: str, summaries: dict, as_of: datetime) -> bool:
    """Persist one immutable closed-day summary; existing days are untouched."""
    history = load_daily_history(root)
    if day in history["days"]:
        return False
    if not any(row["paired_ba"]["signals"] for row in summaries.values()):
        return False
    if any(row["open_pairs"] for row in summaries.values()):
        return False
    history["days"][day] = summaries
    history["updated_at"] = as_of.astimezone(timezone.utc).isoformat()
    path = root / HISTORY_NAME
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    return True


def render_history(history: dict, live_day: str, live_summary: dict, days="5", sort="overall", module=None) -> str:
    values = dict(history.get("days", {}))
    values[live_day] = live_summary
    ordered_days = sorted(values)
    if days != "all":
        ordered_days = ordered_days[-max(1, int(days)):]
    strategies = sorted({name for day in ordered_days for name in values[day]})
    if module:
        strategies = [name for name in strategies if name == module]

    def period_return(name, field):
        return sum(
            values[day].get(name, {}).get(field, {}).get("return_pct", 0.0)
            for day in ordered_days
        )

    newest = ordered_days[-1] if ordered_days else live_day
    def key(name):
        current = values.get(newest, {}).get(name, {})
        if sort == "today":
            return current.get("paired_ba", {}).get("return_pct", float("-inf"))
        if sort == "last":
            return period_return(name, "full_last")
        if sort == "drag":
            return period_return(name, "paired_ba") - period_return(name, "paired_last")
        if sort == "coverage":
            return current.get("coverage_pct", -1.0)
        return period_return(name, "paired_ba")
    if sort != "module":
        strategies.sort(key=key, reverse=True)

    lines = [
        f"$5,000 PAIRED BID/ASK DAILY HISTORY — {len(ordered_days)} DAY(S)",
        "Cells: paired B/A return / execution drag; each day independently starts at $5,000",
        "",
    ]
    header = f"{'Module':<22}" + "".join(f"{day[5:]:>18}" for day in ordered_days) + f"{'Overall B/A':>14}"
    lines.extend([header, "-" * len(header)])
    for name in strategies:
        line = f"{name:<22}"
        for day in ordered_days:
            row = values[day].get(name)
            if not row:
                cell = "-"
            else:
                ba = row["paired_ba"]["return_pct"]
                drag = ba - row["paired_last"]["return_pct"]
                cell = f"{ba:+.2f}%/{drag:+.2f}%"
            line += f"{cell:>18}"
        line += f"{period_return(name, 'paired_ba'):>+13.2f}%"
        lines.append(line)
    return "\n".join(lines) + "\n"


def build_snapshot(root: Path, day: str | None = None, as_of: datetime | None = None):
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    day = day or as_of.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    marks = load_market_marks(root, day, as_of, include_last=True)
    parent_rows, parent_unpriced, sequences = load_snapshot_rows(
        root / "paper_signal_outcomes.jsonl", marks, day, as_of
    )
    # Maintenance rotates completed parent trades into exact gzip archives.
    # Merge them by setup ID so historical days remain reconstructible without
    # requiring a user to save terminal output every evening.
    archived = []
    current_day = as_of.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    # Today's authoritative ledger has not yet been rotated. Avoid rescanning
    # every historical gzip archive on each intraday terminal request.
    if day != current_day:
        for path in sorted((root / "archive").glob("paper_trades.*.jsonl.gz")):
            try:
                rows, exact = load_archive(path)
            except (EOFError, OSError, zlib.error):
                continue
            if exact:
                archived.extend(row for row in rows if market_day(row) == day)
    merged = {str(row.get("setup_id") or ""): row for row in archived}
    merged.update({str(row.get("setup_id") or ""): row for row in parent_rows})
    parent_rows = list(merged.values())
    sequences.update({
        str(row.get("setup_id") or ""): int(row["entry_sequence"])
        for row in archived
        if row.get("setup_id") and row.get("entry_sequence") is not None
    })
    bids = persisted_bids(marks)
    bids.update(load_current_bids(root, day, as_of))
    ba_rows, ba_unpriced = load_bidask_rows(
        root / "paper_signal_v3_bidask_repricing_outcomes.jsonl",
        bids,
        day,
        as_of,
        sequences,
    )
    return day, as_of, parent_rows, ba_rows, parent_unpriced, ba_unpriced


def finalize_day(root: Path, day: str, as_of: datetime | None = None) -> bool:
    day, as_of, parent_rows, ba_rows, _, _ = build_snapshot(root, day, as_of)
    return save_finalized_day(root, day, summarize_paired(parent_rows, ba_rows), as_of)


def build_report(
    root: Path,
    day: str | None = None,
    as_of: datetime | None = None,
    *,
    days: str = "5",
    sort: str = "overall",
    module: str | None = None,
    detail: bool = False,
) -> str:
    day, as_of, parent_rows, ba_rows, parent_unpriced, ba_unpriced = build_snapshot(
        root, day, as_of
    )
    summary = summarize_paired(parent_rows, ba_rows)
    if detail:
        return render(parent_rows, ba_rows, day, as_of, parent_unpriced, ba_unpriced)
    return render_history(load_daily_history(root), day, summary, days, sort, module)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/data"))
    parser.add_argument("--day", help="Market day (YYYY-MM-DD); defaults to today in New York")
    parser.add_argument("--days", default="5", help="Number of recent sessions, or 'all'")
    parser.add_argument(
        "--sort", default="overall",
        choices=("today", "overall", "last", "drag", "coverage", "module"),
    )
    parser.add_argument("--module", help="Show only one exact module ID")
    parser.add_argument("--detail", action="store_true", help="Show today's paired audit table")
    args = parser.parse_args()
    try:
        if args.days != "all":
            if int(args.days) < 1:
                raise ValueError
    except ValueError:
        parser.error("--days must be a positive integer or 'all'")
    print(build_report(
        args.root, args.day, days=args.days, sort=args.sort,
        module=args.module, detail=args.detail,
    ), end="")


if __name__ == "__main__":
    main()
