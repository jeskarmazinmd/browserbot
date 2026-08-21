"""Small, failure-isolated health reporter for the live bot.

This process deliberately does not calculate paper outcomes.  The former
reporting engine mixed outcome simulation, history maintenance, and rendering
in one cycle; one expensive strategy block could therefore prevent every
health file from updating.  This module only reads small status files and
procfs, then atomically publishes a heartbeat.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
from zoneinfo import ZoneInfo


RUN_MODE = os.environ.get("RUN_MODE", "LIVE")
RUN_ID = os.environ.get("RUN_ID", "live")
POLL_SECONDS = max(5.0, float(os.environ.get("REPORTING_POLL_SECONDS", "30")))
REPORTER_ONCE = os.environ.get("REPORTER_ONCE", "0") == "1"

if RUN_MODE == "REPLAY":
    OUTPUT_ROOT = Path("./replay") / RUN_ID
else:
    OUTPUT_ROOT = Path("/data")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

SUMMARY_TXT = OUTPUT_ROOT / "bot_output.txt"
PERFORMANCE_TXT = OUTPUT_ROOT / "strategy_performance_table.txt"
HEARTBEAT_JSON = OUTPUT_ROOT / "reporting_health.json"
RESOURCE_PEAKS_JSON = OUTPUT_ROOT / "resource_daily_peaks.json"
MAINTENANCE_STATUS_JSON = OUTPUT_ROOT / "data_maintenance_status.json"
ERRORS_JSONL = OUTPUT_ROOT / "reporting_errors.jsonl"
EVENTS_JSONL = OUTPUT_ROOT / "bot_events.jsonl"
HISTORY_JSONL = OUTPUT_ROOT / "bot_history.jsonl"
ELIGIBILITY_STATUS_PATH = Path("/data/eligibility_status.json")
TOKEN_PATHS = {
    "market_data": Path("/data/schwab_token.json"),
    "trading": Path("/data/schwab_trade_token.json"),
}
EXPECTED_WORKERS = {
    "collector": "live_quote_collector.py",
    "strategy": "live_strategy_runner.py",
    "reporter": "leaderboard_writer.py",
    "performance": "reporting.capital_performance_worker",
    "dashboard": "schwab_bot_dashboard.dashboard.app:app",
    "supervisor": "supervisor.py",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return "missing"


def age_seconds(path: Path, now: float | None = None) -> float | None:
    try:
        return max(0.0, (time.time() if now is None else now) - path.stat().st_mtime)
    except OSError:
        return None


def fmt_bytes(value: int | float) -> str:
    number = float(value)
    for unit in ("B", "K", "M", "G", "T"):
        if number < 1024:
            return f"{number:.0f}{unit}"
        number /= 1024
    return f"{number:.0f}P"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def update_resource_peaks(snapshot: dict) -> dict:
    """Persist bounded daily high-water marks from the reporter samples."""
    day = utc_now().astimezone(ZoneInfo("America/New_York")).date().isoformat()
    try:
        payload = json.loads(RESOURCE_PEAKS_JSON.read_text())
    except (OSError, ValueError, TypeError):
        payload = {"days": {}}
    days = payload.setdefault("days", {})
    current = days.setdefault(day, {})
    measures = {
        "cpu_pressure_pct": snapshot["cpu"].get("pressure_estimate_pct"),
        "load_1m": snapshot["cpu"].get("load_1m"),
        "memory_used_pct": snapshot["memory"].get("used_pct"),
        "storage_used_pct": snapshot["storage"].get("used_pct"),
        "storage_used_bytes": snapshot["storage"].get("used_bytes"),
    }
    for key, value in measures.items():
        if value is not None:
            current[key] = max(float(value), float(current.get(key, value)))
    current["last_sample_at"] = snapshot["timestamp"]
    # Seven tiny daily records are enough for operational trend context.
    payload["days"] = {key: days[key] for key in sorted(days)[-7:]}
    payload["updated_at"] = snapshot["timestamp"]
    atomic_write_json(RESOURCE_PEAKS_JSON, payload)
    return current


def record_error(stage: str, exc: BaseException) -> None:
    payload = {
        "timestamp": utc_now().isoformat(),
        "stage": stage,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    try:
        ERRORS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with ERRORS_JSONL.open("a") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        pass
    print(f"HEALTH_REPORTER_ERROR {json.dumps(payload, sort_keys=True)}", flush=True)


def worker_status() -> dict[str, dict]:
    found = {name: [] for name in EXPECTED_WORKERS}
    proc_root = Path("/proc")
    if not proc_root.exists():
        return {name: {"status": "UNKNOWN", "pids": []} for name in found}

    for cmdline_path in proc_root.glob("[0-9]*/cmdline"):
        try:
            raw_command = cmdline_path.read_bytes().split(b"\0")
            command_parts = [
                part.decode("utf-8", errors="replace")
                for part in raw_command
                if part
            ]
            pid = int(cmdline_path.parent.name)
        except (OSError, ValueError):
            continue
        for name, needle in EXPECTED_WORKERS.items():
            if needle in command_parts:
                found[name].append(pid)

    return {
        name: {"status": "RUNNING" if pids else "MISSING", "pids": sorted(pids)}
        for name, pids in found.items()
    }


def cpu_status() -> dict:
    try:
        load1, load5, load15 = map(float, Path("/proc/loadavg").read_text().split()[:3])
        count = os.cpu_count() or 1
        pressure = load1 / count * 100.0
        if pressure < 70:
            state = "OK"
        elif pressure < 100:
            state = "BUSY"
        elif pressure < 150:
            state = "HIGH"
        else:
            state = "OVERLOADED"
        return {
            "status": state,
            "logical_cpus": count,
            "pressure_estimate_pct": round(pressure, 1),
            "load_1m": load1,
            "load_5m": load5,
            "load_15m": load15,
        }
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def memory_status() -> dict:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            fields = raw.strip().split()
            if fields:
                values[key] = int(fields[0]) * 1024
        total = int(values.get("MemTotal", 0))
        available = int(values.get("MemAvailable", values.get("MemFree", 0)))
        used = max(0, total - available)
        return {
            "status": "OK" if total and used / total < 0.80 else "HIGH",
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "used_pct": round(used / total * 100.0, 1) if total else None,
        }
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def storage_status() -> dict:
    target = Path("/data") if Path("/data").exists() else OUTPUT_ROOT
    try:
        usage = shutil.disk_usage(target)
        pct = usage.used / usage.total * 100.0 if usage.total else 0.0
        return {
            "status": "OK" if pct < 75 else ("HIGH" if pct < 85 else "CRITICAL"),
            "path": str(target),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "available_bytes": usage.free,
            "used_pct": round(pct, 1),
        }
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def token_status(path: Path) -> dict:
    if not path.exists():
        return {"status": "BROKEN", "path": str(path), "reason": "token file missing"}
    try:
        data = json.loads(path.read_text())
        token = data.get("token") if isinstance(data.get("token"), dict) else data
        created = float(data.get("creation_timestamp", 0) or 0)
        expires = float(token.get("expires_at", 0) or data.get("expires_at", 0) or 0)
        has_access = bool(token.get("access_token") or data.get("access_token"))
        has_refresh = bool(token.get("refresh_token") or data.get("refresh_token"))
        now = time.time()
        access_minutes = (expires - now) / 60.0 if expires else None
        refresh_days = ((created + 7 * 86400) - now) / 86400.0 if created else None

        if not has_access:
            status = "BROKEN"
            reason = "access token missing"
        elif not has_refresh:
            status = "BROKEN" if access_minutes is None or access_minutes <= 0 else "WARNING"
            reason = "refresh token missing"
        elif refresh_days is not None and refresh_days <= 0:
            status = "BROKEN"
            reason = "manual reauthentication overdue"
        elif access_minutes is not None and access_minutes < 10:
            status = "WARNING"
            reason = "access token near expiry; SDK refresh expected"
        else:
            status = "OK"
            reason = "token material present"

        return {
            "status": status,
            "reason": reason,
            "path": str(path),
            "modified_utc": iso_mtime(path),
            "has_access_token": has_access,
            "has_refresh_token": has_refresh,
            "access_minutes_left": round(access_minutes, 1) if access_minutes is not None else None,
            "manual_reauth_days_left": round(refresh_days, 2) if refresh_days is not None else None,
        }
    except Exception as exc:
        return {
            "status": "BROKEN",
            "path": str(path),
            "reason": f"{type(exc).__name__}: {exc}",
        }


def eligibility_status() -> dict:
    if not ELIGIBILITY_STATUS_PATH.exists():
        return {"status": "UNKNOWN", "reason": "eligibility status file missing"}
    try:
        data = json.loads(ELIGIBILITY_STATUS_PATH.read_text())
        return {
            "status": data.get("status", "UNKNOWN"),
            "symbols": data.get("symbol_count"),
            "cache_date": data.get("cache_date"),
            "source": "FALLBACK" if data.get("used_fallback") else "TODAY",
        }
    except Exception as exc:
        return {"status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}


def latest_tape_status(now: float) -> dict:
    tape_dir = OUTPUT_ROOT / "tapes"
    tapes = list(tape_dir.glob("quotes_*.csv")) if tape_dir.exists() else []
    if not tapes:
        return {"status": "MISSING", "path": None, "age_seconds": None}
    latest = max(tapes, key=lambda item: item.stat().st_mtime)
    age = age_seconds(latest, now)
    status = "OK" if age is not None and age <= 10 else "STALE"
    return {
        "status": status,
        "path": str(latest),
        "modified_utc": iso_mtime(latest),
        "age_seconds": round(age, 1) if age is not None else None,
        "size_bytes": latest.stat().st_size,
    }


def build_snapshot() -> dict:
    started = time.monotonic()
    now_dt = utc_now()
    now = now_dt.timestamp()
    workers = worker_status()
    tape = latest_tape_status(now)
    events_age = age_seconds(EVENTS_JSONL, now)
    history_age = age_seconds(HISTORY_JSONL, now)
    warnings = []

    for name, detail in workers.items():
        if detail["status"] != "RUNNING":
            warnings.append(f"worker missing: {name}")
    if tape["status"] != "OK":
        warnings.append(f"quote tape: {tape['status']}")

    tokens = {name: token_status(path) for name, path in TOKEN_PATHS.items()}
    for name, detail in tokens.items():
        if detail["status"] != "OK":
            warnings.append(f"{name} auth: {detail['status']} ({detail.get('reason', 'unknown')})")

    cpu = cpu_status()
    memory = memory_status()
    storage = storage_status()
    for label, detail in (("cpu", cpu), ("memory", memory), ("storage", storage)):
        if detail.get("status") != "OK":
            warnings.append(f"{label}: {detail.get('status')}")

    snapshot = {
        "timestamp": now_dt.isoformat(),
        "status": "WARNING" if warnings else "OK",
        "warnings": warnings,
        "workers": workers,
        "quote_tape": tape,
        "events": {
            "path": str(EVENTS_JSONL),
            "modified_utc": iso_mtime(EVENTS_JSONL),
            "age_seconds": round(events_age, 1) if events_age is not None else None,
            "note": "event age may grow normally when no strategy emits an event",
        },
        "runner_history": {
            "path": str(HISTORY_JSONL),
            "modified_utc": iso_mtime(HISTORY_JSONL),
            "age_seconds": round(history_age, 1) if history_age is not None else None,
        },
        "eligibility": eligibility_status(),
        "tokens": tokens,
        "cpu": cpu,
        "memory": memory,
        "storage": storage,
        "performance_reporting": {
            "status": "DISABLED_DURING_REBUILD",
            "reason": "legacy outcome simulation was removed from the health heartbeat",
        },
    }
    snapshot["generation_seconds"] = round(time.monotonic() - started, 4)
    return snapshot


def _line(label: str, value) -> str:
    return f"{label}: {value}"


def fmt_age(value) -> str:
    return "unknown" if value is None else f"{value}s"


def render_summary(snapshot: dict) -> str:
    lines = [
        "BOT HEALTH OUTPUT — MINIMAL REPORTER",
        _line("Last update", snapshot["timestamp"]),
        _line("Status", snapshot["status"]),
        _line("Generation time", f"{snapshot['generation_seconds']:.4f}s"),
        "",
        "WORKERS",
    ]
    for name, detail in snapshot["workers"].items():
        lines.append(f"{name}: {detail['status']} | pids={detail['pids']}")

    tape = snapshot["quote_tape"]
    lines.extend([
        "",
        "DATA HEARTBEATS",
        f"quote_tape: {tape['status']} | age={fmt_age(tape.get('age_seconds'))} | "
        f"size={fmt_bytes(tape.get('size_bytes', 0))} | path={tape.get('path')}",
        f"events: modified={snapshot['events']['modified_utc']} | "
        f"age={fmt_age(snapshot['events']['age_seconds'])}",
        f"runner_history: modified={snapshot['runner_history']['modified_utc']} | "
        f"age={fmt_age(snapshot['runner_history']['age_seconds'])}",
        "",
        "ELIGIBILITY",
    ])
    eligibility = snapshot["eligibility"]
    lines.append(
        f"status={eligibility.get('status')} | symbols={eligibility.get('symbols')} | "
        f"cache_date={eligibility.get('cache_date')} | source={eligibility.get('source')}"
    )

    lines.extend(["", "AUTHENTICATION"])
    for name, detail in snapshot["tokens"].items():
        lines.append(
            f"{name}: {detail['status']} | {detail.get('reason')} | "
            f"access_minutes_left={detail.get('access_minutes_left')} | "
            f"manual_reauth_days_left={detail.get('manual_reauth_days_left')}"
        )

    cpu = snapshot["cpu"]
    memory = snapshot["memory"]
    storage = snapshot["storage"]
    peaks = snapshot.get("resource_peaks", {})
    lines.extend([
        "",
        "RESOURCES",
        f"cpu: {cpu.get('status')} | logical_cpus={cpu.get('logical_cpus')} | "
        f"pressure_estimate={cpu.get('pressure_estimate_pct')}% | "
        f"load={cpu.get('load_1m')} / {cpu.get('load_5m')} / {cpu.get('load_15m')}",
        f"memory: {memory.get('status')} | used={fmt_bytes(memory.get('used_bytes', 0))} / "
        f"{fmt_bytes(memory.get('total_bytes', 0))} ({memory.get('used_pct')}%) | "
        f"available={fmt_bytes(memory.get('available_bytes', 0))}",
        f"storage: {storage.get('status')} | used={fmt_bytes(storage.get('used_bytes', 0))} / "
        f"{fmt_bytes(storage.get('total_bytes', 0))} ({storage.get('used_pct')}%) | "
        f"available={fmt_bytes(storage.get('available_bytes', 0))}",
        "daily_peaks: "
        f"cpu_pressure={peaks.get('cpu_pressure_pct')}% | "
        f"load_1m={peaks.get('load_1m')} | "
        f"memory={peaks.get('memory_used_pct')}% | "
        f"storage={peaks.get('storage_used_pct')}%",
        "",
        "PERFORMANCE REPORTING",
        "capital_constrained: ISOLATED_WORKER",
        "history: /data/capital_constrained_history.txt",
        "all_engine_performance: OPTIONAL_ISOLATED_WORKER",
        "live: /data/all_engine_performance_live.txt",
        "all_engine_history: /data/all_engine_daily_history.txt",
        "legacy_signal_table: DISABLED_DURING_REBUILD",
    ])

    if snapshot["warnings"]:
        lines.extend(["", "WARNINGS"])
        lines.extend(f"- {warning}" for warning in snapshot["warnings"])
    return "\n".join(lines) + "\n"


def render_performance_placeholder(snapshot: dict) -> str:
    return "\n".join([
        "STRATEGY PERFORMANCE — TEMPORARILY UNAVAILABLE",
        f"Last update: {snapshot['timestamp']}",
        "Status: DISABLED_DURING_REBUILD",
        "",
        "The legacy all-in-one outcome simulator was removed from the health heartbeat because it stalled.",
        "Existing event and outcome ledgers remain preserved under /data.",
        "This file will be restored by the isolated incremental performance worker.",
        "Do not interpret the pre-rebuild table as current.",
        "",
    ])


def run_cycle() -> dict:
    snapshot = build_snapshot()
    snapshot["resource_peaks"] = update_resource_peaks(snapshot)
    atomic_write_json(HEARTBEAT_JSON, snapshot)
    atomic_write_text(SUMMARY_TXT, render_summary(snapshot))
    atomic_write_text(PERFORMANCE_TXT, render_performance_placeholder(snapshot))
    print(
        "HEALTH_REPORTER "
        f"status={snapshot['status']} generation={snapshot['generation_seconds']:.4f}s "
        f"path={SUMMARY_TXT}",
        flush=True,
    )
    return snapshot


def main() -> None:
    print(
        f"health reporter starting poll_seconds={POLL_SECONDS:.1f} output_root={OUTPUT_ROOT}",
        flush=True,
    )
    while True:
        cycle_started = time.monotonic()
        try:
            run_cycle()
        except Exception as exc:
            record_error("run_cycle", exc)
        if REPORTER_ONCE:
            return
        remaining = max(0.0, POLL_SECONDS - (time.monotonic() - cycle_started))
        time.sleep(remaining)


if __name__ == "__main__":
    main()
