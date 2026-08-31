"""Self-describing runtime metadata and heartbeat helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time


MANIFEST_SCHEMA_VERSION = 1
HEARTBEAT_SCHEMA_VERSION = 1
MANIFEST_PATH = Path("/data/runtime_manifest.json")
HEARTBEAT_PATH = Path("/data/runtime_heartbeat.json")
HEARTBEAT_WRITE_INTERVAL_SECONDS = float(
    os.environ.get("RUNTIME_HEARTBEAT_WRITE_INTERVAL_SECONDS", "15")
)

_last_heartbeat_write_monotonic = 0.0


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path, payload):
    """Write JSON atomically without leaving a misleading partial document."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def runtime_manifest(*, c3_only, live_order_placement, run_mode):
    strategy_ids = ["C3N25S10"] if c3_only else []
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "written_at": utc_now_iso(),
        "pid": os.getpid(),
        "app": os.environ.get("FLY_APP_NAME", "unknown"),
        "engine_generation": (
            "SHARED_ENGINE_C3_ONLY" if c3_only else "SHARED_ENGINE_RESEARCH"
        ),
        "run_mode": run_mode,
        "strategy_ids": strategy_ids,
        "c3_only": bool(c3_only),
        "live_order_placement_enabled": bool(live_order_placement),
        "canonical_outputs": {
            "status": "/data/paper_signal_status.json",
            "events": "/data/bot_events.jsonl",
            "outcomes": "/data/paper_signal_outcomes.jsonl",
            "daily_history": "/data/all_engine_daily_history.txt",
            "performance": "/data/all_engine_performance_live.txt",
            "heartbeat": str(HEARTBEAT_PATH),
        },
        "legacy_outputs": {
            "status": "/data/c3_live_status.json",
            "events": "/data/c3_live_shadow_v2.jsonl",
            "state": "/data/c3_live_state_v2.json",
            "operations": "/data/c3_live_operations_v2.jsonl",
            "bars": "/data/c3_live_bars_v2.json",
            "warning": "Obsolete SHADOW_V2 artifacts; never use for health checks.",
        },
    }


def write_runtime_manifest(*, c3_only, live_order_placement, run_mode):
    payload = runtime_manifest(
        c3_only=c3_only,
        live_order_placement=live_order_placement,
        run_mode=run_mode,
    )
    atomic_write_json(MANIFEST_PATH, payload)
    return payload


def write_runtime_heartbeat(*, phase, force=False, **details):
    global _last_heartbeat_write_monotonic

    now_monotonic = time.monotonic()
    if (
        not force
        and now_monotonic - _last_heartbeat_write_monotonic
        < HEARTBEAT_WRITE_INTERVAL_SECONDS
    ):
        return None

    payload = {
        "schema_version": HEARTBEAT_SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "pid": os.getpid(),
        "phase": str(phase),
        **details,
    }
    atomic_write_json(HEARTBEAT_PATH, payload)
    _last_heartbeat_write_monotonic = now_monotonic
    return payload
