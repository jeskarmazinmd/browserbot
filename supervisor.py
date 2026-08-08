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
    "leaderboard": [sys.executable, "-u", "leaderboard_writer.py"],
    "performance": [sys.executable, "-u", "-m", "reporting.capital_performance_worker"],
    "strategy": [sys.executable, "-u", "live_strategy_runner.py"],
    "dashboard": [
        sys.executable,
        "-u",
        "-m",
        "uvicorn",
        "schwab_bot_dashboard.dashboard.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ],
}

# Research workers may observe production data, but they are never allowed to
# become part of the production failure domain.  An optional worker that exits
# stays stopped until the next normal machine restart/deploy.
OPTIONAL_WORKERS = {
    "xs_shadow": [sys.executable, "-u", "xs_shadow_worker.py"],
}

EXIT_LOG = Path("/data/worker_supervisor.jsonl")
ELIGIBILITY_REFRESH = [sys.executable, "-u", "refresh_eligible_symbols.py"]
DATA_MAINTENANCE = [sys.executable, "-u", "data_maintenance.py"]
DATA_VOLUME_PATH = Path("/data")
MIN_DATA_VOLUME_USABLE_MB = int(
    os.environ.get("MIN_DATA_VOLUME_USABLE_MB", "1800")
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
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
