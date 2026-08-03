"""Bounded operational diagnostics for research strategy modules."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


class StrategyDiagnostics:
    def __init__(self):
        override = os.environ.get("STRATEGY_DIAGNOSTICS_ROOT")
        root = Path(override) if override else (
            Path("/data")
            if os.environ.get("RUN_MODE", "LIVE") != "REPLAY"
            else Path("./replay") / os.environ.get("RUN_ID", "live")
        )
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            root = Path("./replay") / os.environ.get("RUN_ID", "local")
            root.mkdir(parents=True, exist_ok=True)
        self.path = root / "strategy_runtime_diagnostics.json"
        self.records = {}
        self._dirty = False
        self._last_write = 0.0

    def define(self, strategy_id, status, **details):
        record = self.records.setdefault(str(strategy_id), {})
        record.update({"strategy_id": str(strategy_id), "status": status, **details})
        record.setdefault("evaluation_cycles", 0)
        record.setdefault("symbols_evaluated", 0)
        record.setdefault("signals", 0)
        record.setdefault("errors", 0)
        record.setdefault("nearest_miss", None)
        self._dirty = True

    def evaluated(self, strategy_id, timestamp, symbol_count, signal_count=0, error=None, nearest_miss=None):
        key = str(strategy_id)
        record = self.records.setdefault(key, {"strategy_id": key, "status": "RUNNING"})
        record["status"] = "ERROR" if error else "RUNNING"
        record["last_evaluated"] = str(timestamp)
        record["evaluation_cycles"] = int(record.get("evaluation_cycles", 0)) + 1
        record["symbols_evaluated"] = int(record.get("symbols_evaluated", 0)) + int(symbol_count or 0)
        record["last_symbol_count"] = int(symbol_count or 0)
        record["signals"] = int(record.get("signals", 0)) + int(signal_count or 0)
        if error:
            record["errors"] = int(record.get("errors", 0)) + 1
            record["last_error"] = str(error)
        else:
            record.setdefault("errors", 0)
        if nearest_miss is not None:
            record["nearest_miss"] = nearest_miss
        self._dirty = True

    def parent_state(self, strategy_id, parent_id, parent_signals, derived_signals):
        record = self.records.setdefault(str(strategy_id), {"strategy_id": str(strategy_id)})
        record.update({
            "status": "RUNNING" if parent_signals else "WAITING_PARENT",
            "parent_strategy": str(parent_id),
            "parent_signals": int(parent_signals),
            "signals": int(derived_signals),
            "last_evaluated": datetime.now(timezone.utc).isoformat(),
        })
        parent_nearest = (self.records.get(str(parent_id)) or {}).get("nearest_miss")
        if not parent_signals and parent_nearest:
            record["nearest_miss"] = {
                **dict(parent_nearest),
                "inherited_from_parent": str(parent_id),
            }
        self._dirty = True

    def flush(self, force=False):
        now = time.monotonic()
        if not self._dirty or (not force and now - self._last_write < 60.0):
            return False
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "modules": {key: self.records[key] for key in sorted(self.records)},
        }
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":"), default=str))
        os.replace(temporary, self.path)
        self._last_write = now
        self._dirty = False
        return True


diagnostics = StrategyDiagnostics()
