"""Bounded, verified end-of-day maintenance for durable bot data.

Run only while bot workers are stopped.  The supervisor invokes this before it
starts them.  Outcome compaction is deliberately gated on the paper tracker
reporting zero active positions and the New York EOD cutoff having passed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

from bounded_jsonl import compress_pending


NY = ZoneInfo("America/New_York")
MIN_ROTATE_BYTES = int(os.environ.get("DATA_ROTATE_MIN_BYTES", str(8 * 1024 * 1024)))
ARCHIVE_RETENTION_DAYS = max(1, int(os.environ.get("DATA_ARCHIVE_RETENTION_DAYS", "3")))
EOD_HOUR = int(os.environ.get("EOD_EXIT_HOUR_ET", "15"))
EOD_MINUTE = int(os.environ.get("EOD_EXIT_MINUTE_ET", "55"))


def _atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _market_date(value) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(NY).date().isoformat()
    except (TypeError, ValueError):
        return "unknown"


def _safe_json_lines(path: Path):
    opener = gzip.open if path.suffix == ".gz" else Path.open
    kwargs = {"mode": "rt", "errors": "replace"} if path.suffix == ".gz" else {"errors": "replace"}
    with opener(path, **kwargs) as handle:
        for line in handle:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    yield row
            except (TypeError, ValueError):
                continue


def _open_outcome_setups(path: Path) -> set[str]:
    """Return entries not yet closed, using the ledger as authority.

    This deliberately does not mutate the ledger.  It protects startup from a
    stale status checkpoint after a restart between PAPER_ENTRY/PAPER_EXIT and
    the tracker's next status write.
    """
    if not path.exists() or not path.stat().st_size:
        return set()
    entries = set()
    exits = set()
    for row in _safe_json_lines(path):
        setup = str(row.get("setup_id") or "")
        if not setup:
            continue
        if row.get("event_type") == "PAPER_ENTRY":
            entries.add(setup)
        elif row.get("event_type") == "PAPER_EXIT":
            exits.add(setup)
    return entries - exits


def _gzip_verified(path: Path, destination: Path) -> dict:
    """Create a verified gzip copy, then remove the source."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    source_hash = hashlib.sha256()
    source_bytes = 0
    with path.open("rb") as source, gzip.open(temporary, "wb", compresslevel=6) as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            source_hash.update(chunk)
            source_bytes += len(chunk)
            target.write(chunk)

    restored_hash = hashlib.sha256()
    restored_bytes = 0
    with gzip.open(temporary, "rb") as restored:
        while True:
            chunk = restored.read(1024 * 1024)
            if not chunk:
                break
            restored_hash.update(chunk)
            restored_bytes += len(chunk)
    if restored_bytes != source_bytes or restored_hash.digest() != source_hash.digest():
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"gzip verification failed for {path}")
    os.replace(temporary, destination)
    path.unlink()
    return {
        "source_bytes": source_bytes,
        "archive_bytes": destination.stat().st_size,
        "sha256": source_hash.hexdigest(),
        "archive": str(destination),
    }


def _summarize_events(path: Path, additional_paths=()) -> dict:
    by_date = defaultdict(Counter)
    by_strategy = defaultdict(Counter)
    rows = 0
    invalid = 0
    for source in (path, *additional_paths):
        opener = gzip.open if source.suffix == ".gz" else Path.open
        kwargs = {"mode": "rt", "errors": "replace"} if source.suffix == ".gz" else {"errors": "replace"}
        with opener(source, **kwargs) as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("not an object")
                except (TypeError, ValueError):
                    invalid += 1
                    continue
                rows += 1
                day = _market_date(row.get("timestamp"))
                event = str(row.get("event_type") or "UNKNOWN")
                strategy = str(row.get("strategy_id") or "UNASSIGNED")
                by_date[day][event] += 1
                by_strategy[day][f"{strategy}|{event}"] += 1
    return {
        "rows": rows,
        "invalid_rows": invalid,
        "event_counts_by_market_date": {day: dict(counts) for day, counts in by_date.items()},
        "strategy_event_counts_by_market_date": {
            day: dict(counts) for day, counts in by_strategy.items()
        },
    }


def _summarize_history(path: Path, additional_paths=()) -> dict:
    by_date = Counter()
    statuses = Counter()
    rows = 0
    invalid = 0
    for source in (path, *additional_paths):
        for row in _safe_json_lines(source):
            rows += 1
            by_date[_market_date(row.get("timestamp"))] += 1
            statuses[str(row.get("status") or "UNKNOWN")] += 1
    # Count malformed lines separately without retaining their contents.
    total_lines = 0
    for source in (path, *additional_paths):
        opener = gzip.open if source.suffix == ".gz" else Path.open
        kwargs = {"mode": "rt", "errors": "replace"} if source.suffix == ".gz" else {"errors": "replace"}
        with opener(source, **kwargs) as handle:
            total_lines += sum(1 for line in handle if line.strip())
    invalid = total_lines - rows
    return {
        "rows": rows,
        "invalid_rows": max(0, invalid),
        "rows_by_market_date": dict(by_date),
        "status_counts": dict(statuses),
    }


def _compact_outcomes(path: Path, destination: Path) -> dict:
    entries = set()
    entry_sequence = {}
    exit_setups = set()
    invalid = 0
    strategies = Counter()
    reasons = Counter()
    pnl = defaultdict(float)
    wins = Counter()
    losses = Counter()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    with gzip.open(temporary, "wt", compresslevel=6) as handle:
        for row in _safe_json_lines(path):
            setup = str(row.get("setup_id") or "")
            if not setup:
                invalid += 1
                continue
            event = row.get("event_type")
            if event == "PAPER_ENTRY":
                if setup not in entries:
                    entry_sequence[setup] = len(entry_sequence)
                entries.add(setup)
                continue
            if event != "PAPER_EXIT":
                continue
            if setup in exit_setups:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"duplicate PAPER_EXIT for setup {setup}")
            exit_setups.add(setup)
            strategy = str(row.get("strategy_id") or "UNKNOWN")
            reason = str(row.get("exit_reason") or "UNKNOWN")
            value = float(row.get("pnl") or 0.0)
            strategies[strategy] += 1
            reasons[f"{strategy}|{reason}"] += 1
            pnl[strategy] += value
            wins[strategy] += value > 0
            losses[strategy] += value < 0
            row = dict(row)
            row["entry_sequence"] = entry_sequence.get(setup)
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    missing_exits = entries - exit_setups
    orphan_exits = exit_setups - entries
    if missing_exits or orphan_exits:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            "outcome ledger is not fully closed: "
            f"entries_without_exit={len(missing_exits)} exits_without_entry={len(orphan_exits)}"
        )
    os.replace(temporary, destination)

    verified = 0
    with gzip.open(destination, "rt", errors="replace") as handle:
        for line in handle:
            json.loads(line)
            verified += 1
    if verified != len(exit_setups):
        destination.unlink(missing_ok=True)
        raise RuntimeError("compact outcome count verification failed")
    return {
        "entry_count": len(entries),
        "exit_count": len(exit_setups),
        "invalid_rows": invalid,
        "archive": str(destination),
        "archive_bytes": destination.stat().st_size,
        "strategy_trades": dict(strategies),
        "strategy_exit_reasons": dict(reasons),
        "strategy_pnl": {key: round(value, 6) for key, value in pnl.items()},
        "strategy_wins": dict(wins),
        "strategy_losses": dict(losses),
    }


def _prune_archives(archive_root: Path) -> list[str]:
    files = sorted(
        (item for item in archive_root.glob("*.gz") if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    removed = []
    # Retention is per artifact family, not a global file count.
    families = defaultdict(list)
    for item in files:
        family = item.name.split(".", 1)[0]
        families[family].append(item)
    for family_files in families.values():
        for item in family_files[ARCHIVE_RETENTION_DAYS:]:
            removed.append(str(item))
            item.unlink()
    return removed


def _prune_intraday(archive_root: Path) -> list[str]:
    root = archive_root / "intraday"
    if not root.exists():
        return []
    directories = sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.name,
        reverse=True,
    )
    removed = []
    for directory in directories[ARCHIVE_RETENTION_DAYS:]:
        removed.append(str(directory))
        shutil.rmtree(directory)
    return removed


def run(data_root="/data", now=None) -> dict:
    root = Path(data_root)
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(NY)
    report = {
        "timestamp": now.isoformat(),
        "market_date": now_et.date().isoformat(),
        "status": "SKIPPED",
        "actions": {},
    }
    # Workers are stopped when the supervisor calls us, so recover any segment
    # whose compressor was interrupted even when it is not yet EOD.
    report["recovered_intraday_segments"] = compress_pending(root / "archive" / "intraday")
    if (now_et.hour, now_et.minute) < (EOD_HOUR, EOD_MINUTE):
        report["reason"] = "before EOD cutoff"
        return report

    status_path = root / "paper_signal_status.json"
    try:
        status = json.loads(status_path.read_text())
    except (OSError, ValueError, TypeError) as exc:
        report["reason"] = f"paper status unavailable: {type(exc).__name__}"
        return report
    outcome_path = root / "paper_signal_outcomes.jsonl"
    open_setups = _open_outcome_setups(outcome_path)
    if open_setups:
        # The append-only ledger is authoritative.  Repair only the derived
        # count; the tracker will recover the actual records and close them by
        # its normal target/stop/EOD rules after the workers start.
        old_active = status.get("active")
        status["active"] = len(open_setups)
        if old_active != len(open_setups):
            _atomic_json(status_path, status)
            report["status_repair"] = {
                "old_active": old_active,
                "new_active": len(open_setups),
                "source": "authoritative_outcome_ledger",
            }
        report["reason"] = f"paper outcomes still active in ledger: {len(open_setups)}"
        return report
    if int(status.get("active", -1)) != 0:
        report["reason"] = f"paper outcomes still active: {status.get('active')}"
        return report

    marker = root / "maintenance" / f"completed_{now_et.date().isoformat()}.json"
    if marker.exists():
        report["reason"] = "already completed for market date"
        return report

    archive = root / "archive"
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    if outcome_path.exists() and outcome_path.stat().st_size:
        compact = archive / f"paper_trades.{stamp}.jsonl.gz"
        report["actions"]["paper_outcomes"] = _compact_outcomes(outcome_path, compact)
        # The compact archive contains every completed setup's full exit row,
        # including its entry fields, so the redundant entry+exit ledger can go.
        outcome_path.unlink()
        outcome_path.touch()

    for name, summarizer in (
        ("bot_events.jsonl", _summarize_events),
        ("bot_history.jsonl", _summarize_history),
    ):
        path = root / name
        if not path.exists() or path.stat().st_size < MIN_ROTATE_BYTES:
            continue
        segment_dir = archive / "intraday" / now_et.date().isoformat()
        segments = sorted(segment_dir.glob(f"{path.stem}.*.jsonl.gz")) if segment_dir.exists() else []
        summary = summarizer(path, segments)
        summary_path = archive / f"{name.removesuffix('.jsonl')}.{stamp}.summary.json"
        _atomic_json(summary_path, summary)
        destination = archive / f"{name.removesuffix('.jsonl')}.{stamp}.jsonl.gz"
        detail = _gzip_verified(path, destination)
        detail["summary"] = str(summary_path)
        detail["daily_rows_including_intraday_segments"] = summary["rows"]
        report["actions"][name] = detail
        path.touch()

    report["removed_expired_archives"] = _prune_archives(archive)
    report["removed_expired_intraday"] = _prune_intraday(archive)
    report["status"] = "COMPLETED"
    report["reason"] = "verified EOD maintenance complete"
    _atomic_json(marker, report)
    _atomic_json(root / "data_maintenance_status.json", report)
    return report


def main() -> int:
    try:
        result = run(os.environ.get("DATA_ROOT", "/data"))
        print(f"DATA_MAINTENANCE {json.dumps(result, sort_keys=True)}", flush=True)
        return 0
    except Exception as exc:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(f"DATA_MAINTENANCE {json.dumps(payload, sort_keys=True)}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
