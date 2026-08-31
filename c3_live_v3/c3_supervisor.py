"""Run production workers with isolated optional research workers.

Critical worker failure remains a single failure domain: if any production
worker exits, terminate its siblings and let Fly restart a clean machine.
Optional research workers are isolated so an experimental failure cannot
bring production down.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import signal
import shutil
import subprocess
import sys
import time


WORKERS = {
    "collector": [sys.executable, "-u", "live_quote_collector.py"],
    "strategy": [sys.executable, "-u", "live_strategy_runner.py"],
}

# Research workers may observe production data, but they are never allowed to
# become part of the production failure domain.  An optional worker that exits
# stays stopped until the next normal machine restart/deploy.
OPTIONAL_WORKERS = {
    "capital_performance": [
        sys.executable,
        "-u",
        "-m",
        "reporting.capital_performance_worker",
    ],
    "all_engine_performance": [
        sys.executable,
        "-u",
        "-m",
        "reporting.all_engine_performance_worker",
    ],
}

EXIT_LOG = Path("/data/worker_supervisor.jsonl")
ELIGIBILITY_REFRESH = [sys.executable, "-u", "refresh_eligible_symbols.py"]
DATA_MAINTENANCE = [sys.executable, "-u", "data_maintenance.py"]
DATA_VOLUME_PATH = Path("/data")
MIN_DATA_VOLUME_USABLE_MB = int(
    os.environ.get("MIN_DATA_VOLUME_USABLE_MB", "1800")
)
STRATEGY_HEARTBEAT = Path("/data/runtime_heartbeat.json")
STRATEGY_HEARTBEAT_TIMEOUT_SECONDS = float(
    os.environ.get("STRATEGY_HEARTBEAT_TIMEOUT_SECONDS", "180")
)
STRATEGY_HEARTBEAT_STARTUP_GRACE_SECONDS = float(
    os.environ.get("STRATEGY_HEARTBEAT_STARTUP_GRACE_SECONDS", "600")
)


def record(event, **details):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
    }
    line = json.dumps(payload, sort_keys=True)
    print(f"SUPERVISOR {line}", flush=True)
    try:
        EXIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with EXIT_LOG.open("a") as handle:
            handle.write(line + "\n")
    except Exception as exc:
        print(f"SUPERVISOR_LOG_ERROR {type(exc).__name__}: {exc}", flush=True)


def terminate_all(processes):
    for proc in processes.values():
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 10
    while time.time() < deadline and any(p.poll() is None for p in processes.values()):
        time.sleep(0.1)
    for proc in processes.values():
        if proc.poll() is None:
            proc.kill()


def data_volume_total_mb(path=DATA_VOLUME_PATH):
    return shutil.disk_usage(path).total / (1024 * 1024)


def worker_exit_is_fatal(name):
    """Return whether a child exit must restart the production failure domain."""
    if name in OPTIONAL_WORKERS:
        return False
    return name in WORKERS


def heartbeat_health(path, expected_pid, now=None):
    """Return heartbeat health without confusing a prior process for this one."""
    now = now or datetime.now(timezone.utc)
    try:
        payload = json.loads(Path(path).read_text())
        updated_at = datetime.fromisoformat(
            str(payload["updated_at"]).replace("Z", "+00:00")
        )
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - updated_at).total_seconds()
        heartbeat_pid = int(payload["pid"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return False, {
            "reason": "missing_or_invalid",
            "error": f"{type(exc).__name__}: {exc}",
        }

    if heartbeat_pid != int(expected_pid):
        return False, {
            "reason": "pid_mismatch",
            "heartbeat_pid": heartbeat_pid,
            "expected_pid": int(expected_pid),
            "age_seconds": round(age_seconds, 3),
        }
    if age_seconds > STRATEGY_HEARTBEAT_TIMEOUT_SECONDS:
        return False, {
            "reason": "stale",
            "heartbeat_pid": heartbeat_pid,
            "age_seconds": round(age_seconds, 3),
            "timeout_seconds": STRATEGY_HEARTBEAT_TIMEOUT_SECONDS,
            "phase": payload.get("phase"),
        }
    return True, {
        "heartbeat_pid": heartbeat_pid,
        "age_seconds": round(age_seconds, 3),
        "phase": payload.get("phase"),
    }


def main():
    try:
        volume_total_mb = data_volume_total_mb()
    except OSError as exc:
        record("data_volume_check_failed", error=f"{type(exc).__name__}: {exc}")
        return 1
    if volume_total_mb < MIN_DATA_VOLUME_USABLE_MB:
        record(
            "data_volume_too_small",
            total_mb=round(volume_total_mb, 1),
            minimum_mb=MIN_DATA_VOLUME_USABLE_MB,
        )
        return 1
    record(
        "data_volume_check_ok",
        total_mb=round(volume_total_mb, 1),
        minimum_mb=MIN_DATA_VOLUME_USABLE_MB,
    )

    maintenance = subprocess.run(
        DATA_MAINTENANCE,
        cwd="/app",
        env=os.environ.copy(),
        check=False,
    )
    if maintenance.returncode != 0:
        record("data_maintenance_failed", returncode=maintenance.returncode)
        return 1
    record("data_maintenance_checked")

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    eligibility_cache = Path(f"/data/eligible_symbols_{today}.csv")

    if eligibility_cache.exists() and eligibility_cache.stat().st_size > 0:
        record("eligibility_refresh_skipped", cache=str(eligibility_cache))
    else:
        record("eligibility_refresh_start")
        refresh = subprocess.run(
            ELIGIBILITY_REFRESH,
            cwd="/app",
            env=os.environ.copy(),
            check=False,
        )
        if refresh.returncode != 0:
            record("eligibility_refresh_failed", returncode=refresh.returncode)
            return 1
        record("eligibility_refresh_complete", cache=str(eligibility_cache))

    commands = {**WORKERS, **OPTIONAL_WORKERS}
    processes = {
        name: subprocess.Popen(command, env=os.environ.copy())
        for name, command in commands.items()
    }
    worker_started_monotonic = {
        name: time.monotonic() for name in processes
    }
    record(
        "started",
        workers={name: proc.pid for name, proc in processes.items()},
        optional_workers=sorted(OPTIONAL_WORKERS),
    )

    stopping = False

    def handle_signal(signum, _frame):
        nonlocal stopping
        stopping = True
        record("signal", signal=signum)
        terminate_all(processes)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while True:
        for name, proc in list(processes.items()):
            code = proc.poll()
            if code is None:
                continue
            if not worker_exit_is_fatal(name):
                record("optional_worker_exit", worker=name, returncode=code)
                processes.pop(name, None)
                continue
            record("worker_exit", worker=name, returncode=code)
            terminate_all(processes)
            return 0 if stopping else 1

        strategy = processes.get("strategy")
        if strategy is not None and strategy.poll() is None:
            runtime_seconds = (
                time.monotonic() - worker_started_monotonic["strategy"]
            )
            if runtime_seconds >= STRATEGY_HEARTBEAT_STARTUP_GRACE_SECONDS:
                healthy, details = heartbeat_health(
                    STRATEGY_HEARTBEAT,
                    strategy.pid,
                )
                if not healthy:
                    record(
                        "worker_heartbeat_failed",
                        worker="strategy",
                        runtime_seconds=round(runtime_seconds, 3),
                        **details,
                    )
                    terminate_all(processes)
                    return 1
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
