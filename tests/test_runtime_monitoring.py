from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

import c3_live_v3.c3_supervisor as supervisor
import runtime_monitoring


class RuntimeMonitoringTests(unittest.TestCase):
    def test_manifest_declares_shared_c3_outputs_and_marks_v2_legacy(self):
        previous = os.environ.get("FLY_APP_NAME")
        os.environ["FLY_APP_NAME"] = "schwab-c3-live"
        try:
            manifest = runtime_monitoring.runtime_manifest(
                c3_only=True,
                live_order_placement=False,
                run_mode="LIVE",
            )
        finally:
            if previous is None:
                os.environ.pop("FLY_APP_NAME", None)
            else:
                os.environ["FLY_APP_NAME"] = previous

        self.assertEqual(manifest["engine_generation"], "SHARED_ENGINE_C3_ONLY")
        self.assertEqual(manifest["strategy_ids"], ["C3N25S10"])
        self.assertIs(manifest["live_order_placement_enabled"], False)
        self.assertEqual(
            manifest["canonical_outputs"]["status"],
            "/data/paper_signal_status.json",
        )
        self.assertEqual(
            manifest["legacy_outputs"]["status"],
            "/data/c3_live_status.json",
        )
        self.assertIn("never use", manifest["legacy_outputs"]["warning"])

    def test_supervisor_accepts_fresh_pid_bound_heartbeat(self):
        with tempfile.TemporaryDirectory() as root:
            heartbeat = Path(root) / "heartbeat.json"
            heartbeat.write_text(json.dumps({
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "pid": 123,
                "phase": "CYCLE_COMPLETE",
            }))
            healthy, details = supervisor.heartbeat_health(heartbeat, 123)

        self.assertIs(healthy, True)
        self.assertEqual(details["phase"], "CYCLE_COMPLETE")

    def test_supervisor_rejects_stale_or_wrong_pid_heartbeat(self):
        with tempfile.TemporaryDirectory() as root:
            heartbeat = Path(root) / "heartbeat.json"
            now = datetime.now(timezone.utc)
            heartbeat.write_text(json.dumps({
                "updated_at": (now - timedelta(seconds=181)).isoformat(),
                "pid": 123,
                "phase": "QUOTES_READ",
            }))

            healthy, details = supervisor.heartbeat_health(
                heartbeat,
                123,
                now=now,
            )
            self.assertIs(healthy, False)
            self.assertEqual(details["reason"], "stale")

            healthy, details = supervisor.heartbeat_health(
                heartbeat,
                456,
                now=now,
            )

        self.assertIs(healthy, False)
        self.assertEqual(details["reason"], "pid_mismatch")


if __name__ == "__main__":
    unittest.main()
