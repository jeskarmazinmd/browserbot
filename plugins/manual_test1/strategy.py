from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from strategy_api import TradeIntent


class ManualTestPlugin:
    strategy_id = "MANUAL_TEST1"

    def __init__(self):
        self.path = Path("/data/manual_test1_request.json")

    def evaluate(self, context):
        if not self.path.exists():
            return []
        claimed = self.path.with_name("manual_test1_request.claimed.json")
        self.path.replace(claimed)
        try:
            value = json.loads(claimed.read_text())
            expires = datetime.fromisoformat(value["expires_at"])
            if datetime.now(timezone.utc) > expires:
                return []
            return [TradeIntent(**value)]
        finally:
            claimed.unlink(missing_ok=True)


def create_plugin():
    return ManualTestPlugin()
