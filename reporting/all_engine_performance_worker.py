"""Isolated live and durable all-engine performance worker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from reporting.all_engine_performance import calculate, cutoff_for, render_snapshot


ROOT = Path(os.environ.get("ALL_ENGINE_DATA_ROOT", "/data"))
LIVE_JSON = ROOT / "all_engine_performance_live.json"
LIVE_TXT = ROOT / "all_engine_performance_live.txt"
HISTORY_JSON = ROOT / "all_engine_daily_history.json"
HISTORY_TXT = ROOT / "all_engine_daily_history.txt"
HEALTH = ROOT / "all_engine_performance_health.json"
ERRORS = ROOT / "all_engine_performance_errors.jsonl"
NY = ZoneInfo("America/New_York")
POLL_SECONDS = max(60.0, float(os.environ.get("ALL_ENGINE_PERFORMANCE_POLL_SECONDS", "600")))
FINALIZE_HOUR = int(os.environ.get("ALL_ENGINE_FINALIZE_HOUR_ET", "16"))
FINALIZE_MINUTE = int(os.environ.get("ALL_ENGINE_FINALIZE_MINUTE_ET", "5"))
VERSION = 1
BACKFILL_DAYS = max(1, int(os.environ.get("ALL_ENGINE_BACKFILL_DAYS", "30")))


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value)
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_history():
    try:
        value = json.loads(HISTORY_JSON.read_text())
        if value.get("version") == VERSION and isinstance(value.get("days"), dict):
            return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {"version": VERSION, "days": {}}


def render_history(history):
    days = sorted(history["days"])
    if not days:
        return "ALL-ENGINE DAILY HISTORY\nNo finalized days yet.\n"
    visible = days[-20:]
    names = sorted({name for day in visible for name in history["days"][day]["modules"]})
    lines = [
        "ALL-ENGINE DAILY HISTORY",
        "Cells show fixed-cutoff hypothetical-close return.",
        "",
        f"{'Module':<20}" + "".join(f"{day[5:]:>12}" for day in visible),
    ]
    lines.append("-" * len(lines[-1]))
    for name in names:
        line = f"{name:<20}"
        for day in visible:
            row = history["days"][day]["modules"].get(name)
            line += f"{row['return_pct']:+11.2f}%" if row else f"{'-':>12}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def after_finalize(now_et):
    return (now_et.hour, now_et.minute) >= (FINALIZE_HOUR, FINALIZE_MINUTE)


def discover_backfill_days():
    """Return retained market dates with a primary quote tape."""
    discovered = []
    for path in (ROOT / "tapes").glob("quotes_*.csv"):
        compact = path.stem.removeprefix("quotes_")
        if len(compact) != 8 or not compact.isdigit():
            continue
        discovered.append(f"{compact[:4]}-{compact[4:6]}-{compact[6:]}")
    return sorted(set(discovered))[-BACKFILL_DAYS:]


def finalize_missing_days(history, today, now_et, current_snapshot=None):
    changed = False
    for day in discover_backfill_days():
        if day in history["days"] or day > today:
            continue
        if day == today and not after_finalize(now_et):
            continue
        snapshot = (
            current_snapshot
            if day == today and current_snapshot is not None
            else calculate(ROOT, day=day, as_of=cutoff_for(day) + timedelta(minutes=5))
        )
        history["days"][day] = snapshot
        changed = True
    if changed:
        history["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(HISTORY_JSON, history)
    return changed


def update_once(now=None):
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(NY)
    day = now_et.date().isoformat()
    snapshot = calculate(ROOT, day=day, as_of=now)
    atomic_json(LIVE_JSON, snapshot)
    atomic_text(LIVE_TXT, render_snapshot(snapshot))

    history = load_history()
    finalize_missing_days(history, day, now_et, current_snapshot=snapshot)
    atomic_text(HISTORY_TXT, render_history(history))

    health = {
        "timestamp": now.isoformat(),
        "status": "OK",
        "live_day": day,
        "module_count": snapshot["module_count"],
        "diagnostics": snapshot["diagnostics"],
        "finalized_days": sorted(history["days"]),
        "poll_seconds": POLL_SECONDS,
    }
    atomic_json(HEALTH, health)
    return snapshot, history


def record_error(exc):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_type": type(exc).__name__, "error": str(exc),
    }
    try:
        with ERRORS.open("a") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        atomic_json(HEALTH, {**payload, "status": "ERROR"})
    except OSError:
        pass


def main():
    while True:
        try:
            update_once()
        except Exception as exc:
            record_error(exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
