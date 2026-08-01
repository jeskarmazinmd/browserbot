"""Run all bot workers as one failure domain.

If any worker exits (including an OOM SIGKILL), terminate its siblings and exit
non-zero.  Fly then restarts a clean machine instead of leaving a partially
working bot online with a stale tape.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time


WORKERS = {
    "collector": [sys.executable, "-u", "live_quote_collector.py"],
    "leaderboard": [sys.executable, "-u", "leaderboard_writer.py"],
    "strategy": [sys.executable, "-u", "live_strategy_runner.py"],
}
EXIT_LOG = Path("/data/worker_supervisor.jsonl")


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


def main():
    processes = {
        name: subprocess.Popen(command, env=os.environ.copy())
        for name, command in WORKERS.items()
    }
    record("started", workers={name: proc.pid for name, proc in processes.items()})

    stopping = False

    def handle_signal(signum, _frame):
        nonlocal stopping
        stopping = True
        record("signal", signal=signum)
        terminate_all(processes)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while True:
        for name, proc in processes.items():
            code = proc.poll()
            if code is None:
                continue
            record("worker_exit", worker=name, returncode=code)
            terminate_all(processes)
            return 0 if stopping else 1
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
