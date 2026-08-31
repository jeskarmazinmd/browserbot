"""Print the authoritative health summary for schwab-c3-live."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


MANIFEST_PATH = Path("/data/runtime_manifest.json")


def load_json(path):
    with Path(path).open() as handle:
        return json.load(handle)


def parse_timestamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main():
    if not MANIFEST_PATH.exists():
        print("FAIL runtime manifest missing: /data/runtime_manifest.json")
        return 2

    manifest = load_json(MANIFEST_PATH)
    outputs = manifest.get("canonical_outputs") or {}
    heartbeat_path = Path(outputs.get("heartbeat", "/data/runtime_heartbeat.json"))
    if not heartbeat_path.exists():
        print(f"FAIL runtime heartbeat missing: {heartbeat_path}")
        return 2

    heartbeat = load_json(heartbeat_path)
    heartbeat_age = (
        datetime.now(timezone.utc) - parse_timestamp(heartbeat["updated_at"])
    ).total_seconds()
    status_path = Path(outputs.get("status", ""))
    status = load_json(status_path) if status_path.exists() else None

    safe = manifest.get("live_order_placement_enabled") is False
    current = heartbeat_age <= 180
    healthy = safe and current and bool(manifest.get("c3_only"))

    print(f"health={'OK' if healthy else 'FAIL'}")
    print(f"engine={manifest.get('engine_generation')}")
    print(f"strategies={','.join(manifest.get('strategy_ids') or [])}")
    print(f"run_mode={manifest.get('run_mode')}")
    print(
        "live_order_placement_enabled="
        f"{str(manifest.get('live_order_placement_enabled')).lower()}"
    )
    print(f"runner_pid={heartbeat.get('pid')}")
    print(f"heartbeat_phase={heartbeat.get('phase')}")
    print(f"heartbeat_age_seconds={heartbeat_age:.1f}")
    print(f"canonical_status={status_path}")
    if status is None:
        print("paper_status=missing")
    else:
        print(
            "paper_status="
            f"updated_at={status.get('updated_at')} "
            f"active={status.get('active')} "
            f"completed={status.get('completed')}"
        )
    print("legacy_v2_outputs=IGNORED")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
