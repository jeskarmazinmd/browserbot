"""Isolated end-of-day finite-capital performance worker."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from reporting.capital_performance import simulate_day


ROOT = Path("/data")
LEDGER = ROOT / "paper_signal_outcomes.jsonl"
STATUS = ROOT / "paper_signal_status.json"
ARCHIVE = ROOT / "archive"
HISTORY = ROOT / "capital_constrained_history.json"
HISTORY_TXT = ROOT / "capital_constrained_history.txt"
LATEST_TXT = ROOT / "capital_constrained_performance.txt"
HEALTH = ROOT / "capital_performance_health.json"
ERRORS = ROOT / "capital_performance_errors.jsonl"

NY = ZoneInfo("America/New_York")
POLL_SECONDS = max(
    30.0,
    float(os.environ.get("CAPITAL_PERFORMANCE_POLL_SECONDS", "60")),
)


def atomic_text(path: Path, value: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(value)
    os.replace(tmp, path)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_history() -> dict:
    try:
        value = json.loads(HISTORY.read_text())
        if isinstance(value, dict):
            value.setdefault("days", {})
            value.setdefault("processed_archives", {})
            return value
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "days": {}, "processed_archives": {}}


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def market_day(row: dict):
    value = parse_time(row.get("signal_timestamp"))
    return value.astimezone(NY).date().isoformat() if value else None


def compact_exit(row: dict, sequence):
    return {
        "setup_id": row.get("setup_id"),
        "strategy_id": row.get("strategy_id"),
        "signal_timestamp": row.get("signal_timestamp"),
        "entry_price": row.get("entry_price"),
        "stop_price": row.get("stop_price"),
        "exit_timestamp": row.get("exit_timestamp"),
        "exit_price": row.get("exit_price"),
        "entry_sequence": sequence,
    }


def load_live_exits() -> list[dict]:
    sequence_by_setup = {}
    next_sequence = 0
    exits = []

    try:
        handle = LEDGER.open()
    except OSError:
        return exits

    with handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue

            setup = str(row.get("setup_id") or "")
            event = row.get("event_type")

            if event == "PAPER_ENTRY":
                if setup and setup not in sequence_by_setup:
                    sequence_by_setup[setup] = next_sequence
                    next_sequence += 1
                continue

            if event != "PAPER_EXIT" or not setup:
                continue

            sequence = sequence_by_setup.get(setup)
            if sequence is None:
                continue

            exits.append(compact_exit(row, sequence))

    return exits


def load_archive(path: Path):
    rows = []
    exact = True

    with gzip.open(path, "rt", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if row.get("event_type") != "PAPER_EXIT":
                continue
            sequence = row.get("entry_sequence")
            if sequence is None:
                exact = False
            rows.append(compact_exit(row, sequence))

    return rows, exact


def grouped(rows):
    result = defaultdict(lambda: defaultdict(list))
    for row in rows:
        day = market_day(row)
        strategy = str(row.get("strategy_id") or "")
        if day and strategy:
            result[day][strategy].append(row)
    return result


def summarize(day_rows):
    return {
        strategy: simulate_day(rows)
        for strategy, rows in sorted(day_rows.items())
    }


def status_active():
    try:
        return int(json.loads(STATUS.read_text()).get("active", -1))
    except (OSError, ValueError, TypeError):
        return -1


def after_eod(now_et: datetime) -> bool:
    return (now_et.hour, now_et.minute) >= (16, 0)


def format_hold(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{seconds:02d}s"


def render(history: dict) -> None:
    days = sorted(history["days"])
    if not days:
        atomic_text(
            HISTORY_TXT,
            "$5,000 CAPITAL-CONSTRAINED DAILY HISTORY\nNo finalized days yet.\n",
        )
        return

    latest = days[-1]
    rows = history["days"][latest]
    ranked = sorted(
        rows.items(),
        key=lambda item: item[1]["return_pct"],
        reverse=True,
    )

    lines = [
        f"$5,000 CAPITAL-CONSTRAINED STRATEGY COMPARISON — {latest}",
        "1% equity risk/trade | 20% maximum position | whole shares",
        "No leverage, fees, spread or slippage",
        "",
        (
            f"{'Rank':>4} {'Module':<8} {'Signals':>7} {'Taken':>6} "
            f"{'Skipped':>7} {'End $':>10} {'Return':>8} {'Max DD':>8} "
            f"{'Peak $':>10} {'MaxPos':>7} {'Median':>9} {'1sh Ret':>8}"
        ),
        "-" * 108,
    ]

    for rank, (strategy, row) in enumerate(ranked, 1):
        lines.append(
            f"{rank:>4} {strategy:<8} "
            f"{row['signals']:>7} {row['taken']:>6} {row['skipped']:>7} "
            f"{row['end_equity']:>10.2f} {row['return_pct']:>+7.2f}% "
            f"{row['max_drawdown_pct']:>7.2f}% {row['peak_deployed']:>10.2f} "
            f"{row['max_positions']:>7} "
            f"{format_hold(row['median_hold_seconds']):>9} "
            f"{row['one_share_return_pct']:>+7.2f}%"
        )

    atomic_text(LATEST_TXT, "\n".join(lines) + "\n")

    visible = days[-10:]
    strategies = sorted(
        {
            strategy
            for day in visible
            for strategy in history["days"][day]
        }
    )

    history_lines = [
        "$5,000 CAPITAL-CONSTRAINED DAILY HISTORY",
        "Cells show daily P/L / return. Each day starts from $5,000.",
        "",
    ]
    header = f"{'Strategy':<10}" + "".join(
        f"{day[5:]:>18}" for day in visible
    )
    history_lines.extend([header, "-" * len(header)])

    for strategy in strategies:
        line = f"{strategy:<10}"
        for day in visible:
            row = history["days"][day].get(strategy)
            if row is None:
                cell = "-"
            else:
                pnl = row["end_equity"] - 5000.0
                cell = f"${pnl:+.0f}/{row['return_pct']:+.2f}%"
            line += f"{cell:>18}"
        history_lines.append(line)

    atomic_text(HISTORY_TXT, "\n".join(history_lines) + "\n")


def update_once(scan_live: bool) -> dict:
    history = load_history()
    changed = False

    for path in sorted(ARCHIVE.glob("paper_trades.*.jsonl.gz")):
        name = path.name
        if name in history["processed_archives"]:
            continue

        rows, exact = load_archive(path)
        if not exact:
            history["processed_archives"][name] = "legacy_missing_entry_sequence"
            changed = True
            continue

        for day, strategies in grouped(rows).items():
            if day not in history["days"]:
                history["days"][day] = summarize(strategies)
                changed = True

        history["processed_archives"][name] = "processed_exact"
        changed = True

    if scan_live:
        now_et = datetime.now(timezone.utc).astimezone(NY)
        today = now_et.date().isoformat()
        active = status_active()
        groups = grouped(load_live_exits())

        for day, strategies in groups.items():
            can_finalize = day < today or (
                day == today and after_eod(now_et) and active == 0
            )
            if can_finalize and day not in history["days"]:
                history["days"][day] = summarize(strategies)
                changed = True

    if changed:
        history["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(HISTORY, history)

    render(history)
    return history


def record_error(exc: BaseException) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    try:
        with ERRORS.open("a") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        pass


def main() -> None:
    startup_scan_done = False

    while True:
        try:
            now_et = datetime.now(timezone.utc).astimezone(NY)
            history = load_history()
            today = now_et.date().isoformat()

            scan_live = not startup_scan_done
            if (
                after_eod(now_et)
                and today not in history["days"]
                and status_active() == 0
            ):
                scan_live = True

            history = update_once(scan_live=scan_live)
            startup_scan_done = True

            atomic_json(
                HEALTH,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "OK",
                    "finalized_days": sorted(history["days"]),
                },
            )
        except Exception as exc:
            record_error(exc)
            try:
                atomic_json(
                    HEALTH,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "ERROR",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
            except Exception:
                pass

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
