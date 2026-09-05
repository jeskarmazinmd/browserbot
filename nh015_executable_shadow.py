"""Durable executable-price shadow for C3N25S10NH015.

This tracker observes C3N25S10NH015DUP signals without placing orders. Long
entries require a fresh executable ask at or below the model limit and are
marked at that ask. Open positions are then advanced and exited using the
executable bid.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from live_nh015_execution import nh015_should_exit


STRATEGY_ID = "C3N25S10NH015EXEC"
SOURCE_STRATEGY_ID = "C3N25S10NH015DUP"
NY = ZoneInfo("America/New_York")


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _positive(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


class NH015ExecutableShadow:
    """Paper-only NH015 tracker driven by executable NBBO prices."""

    def __init__(self, data_root: Path, *, eod_hour: int = 15, eod_minute: int = 55):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "nh015_exec_outcomes.jsonl"
        self.state_path = self.root / "nh015_exec_active.json"
        self.status_path = self.root / "nh015_exec_status.json"
        self.eod_hour = int(eod_hour)
        self.eod_minute = int(eod_minute)
        self.active: dict[str, dict[str, Any]] = {}
        self.seen: set[str] = set()
        self.completed = 0
        self.skipped_ask_above_limit = 0
        self.skipped_no_quote = 0
        self._recover()

    @staticmethod
    def _setup_id(signal: Mapping[str, Any], timestamp: datetime) -> str:
        source_setup_id = str(signal.get("setup_id") or "")
        symbol = str(signal.get("symbol") or "").strip().upper()
        source_key = source_setup_id or timestamp.isoformat()
        return f"{STRATEGY_ID}|{symbol}|{source_key}"

    def _append(self, row: Mapping[str, Any]) -> None:
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    @staticmethod
    def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _persist(self) -> None:
        self._atomic_json(
            self.state_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active": list(self.active.values()),
            },
        )
        self._write_status()

    def _write_status(self) -> None:
        self._atomic_json(
            self.status_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "strategy_id": STRATEGY_ID,
                "source_strategy_id": SOURCE_STRATEGY_ID,
                "active": len(self.active),
                "completed": self.completed,
                "seen": len(self.seen),
                "skipped_ask_above_limit": self.skipped_ask_above_limit,
                "skipped_no_quote": self.skipped_no_quote,
            },
        )

    def _recover(self) -> None:
        if self.ledger_path.exists():
            with self.ledger_path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    setup_id = row.get("setup_id")
                    if not setup_id:
                        continue
                    self.seen.add(setup_id)
                    event_type = row.get("event_type")
                    if event_type == "EXEC_ENTRY":
                        self.active[setup_id] = dict(row)
                    elif event_type == "EXEC_EXIT":
                        self.active.pop(setup_id, None)
                        self.completed += 1
                    elif event_type == "EXEC_SKIP":
                        if row.get("reason") == "ASK_ABOVE_LIMIT":
                            self.skipped_ask_above_limit += 1
                        elif row.get("reason") == "NO_EXECUTABLE_QUOTE":
                            self.skipped_no_quote += 1

        # The ledger decides which positions are active. The checkpoint only
        # restores mutable high/timer fields and cannot resurrect an exit.
        if self.state_path.exists():
            try:
                checkpoint = json.loads(self.state_path.read_text())
                saved_records = checkpoint.get("active", [])
            except (OSError, TypeError, ValueError):
                saved_records = []
            for saved in saved_records:
                setup_id = saved.get("setup_id")
                if setup_id in self.active:
                    self.active[setup_id].update(saved)
        self._write_status()

    def symbols(self) -> set[str]:
        return {
            str(record["symbol"]).upper()
            for record in self.active.values()
            if record.get("symbol")
        }

    def register(
        self,
        signal: Mapping[str, Any],
        quote: Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> bool:
        """Evaluate one DUP signal against its contemporaneous executable quote."""
        if str(signal.get("strategy_id") or "") != SOURCE_STRATEGY_ID:
            return False
        try:
            timestamp = _utc(now or signal.get("timestamp"))
        except (TypeError, ValueError):
            return False
        source_setup_id = str(signal.get("setup_id") or "")
        symbol = str(signal.get("symbol") or "").strip().upper()
        model_entry = _positive(signal.get("entry_price"))
        target = _positive(signal.get("target_price"))
        stop = _positive(signal.get("stop_price"))
        if not symbol or model_entry is None or target is None or stop is None:
            return False

        setup_id = self._setup_id(signal, timestamp)
        if setup_id in self.seen:
            return False
        self.seen.add(setup_id)

        bid = _positive((quote or {}).get("bid"))
        ask = _positive((quote or {}).get("ask"))
        if bid is None or ask is None or ask < bid:
            self.skipped_no_quote += 1
            self._record_skip(
                setup_id, source_setup_id, symbol, timestamp, model_entry,
                "NO_EXECUTABLE_QUOTE", quote,
            )
            return False
        if ask > model_entry:
            self.skipped_ask_above_limit += 1
            self._record_skip(
                setup_id, source_setup_id, symbol, timestamp, model_entry,
                "ASK_ABOVE_LIMIT", quote,
            )
            return False

        record = {
            "event_type": "EXEC_ENTRY",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "setup_id": setup_id,
            "strategy_id": STRATEGY_ID,
            "source_strategy_id": SOURCE_STRATEGY_ID,
            "source_setup_id": source_setup_id,
            "symbol": symbol,
            "signal_timestamp": timestamp.isoformat(),
            "entry_timestamp": timestamp.isoformat(),
            "model_entry_price": model_entry,
            "entry_price": ask,
            "actual_entry_price": ask,
            "entry_ask": ask,
            "entry_bid": bid,
            "entry_spread_pct": quote.get("spread_pct"),
            "target_price": target,
            "stop_price": stop,
            "activation_gain_pct": 0.3,
            "no_new_high_seconds": 15.0,
            "nh015_activated": False,
            "nh015_highest_bid": bid,
            "nh015_high_bid_at": None,
            "entry_fill_time": timestamp.isoformat(),
            "last_bid": bid,
            "last_bid_at": timestamp.isoformat(),
        }
        self._append(record)
        self.active[setup_id] = record
        self._persist()
        return True

    def _record_skip(
        self,
        setup_id: str,
        source_setup_id: str,
        symbol: str,
        timestamp: datetime,
        model_entry: float,
        reason: str,
        quote: Mapping[str, Any] | None,
    ) -> None:
        row = {
            "event_type": "EXEC_SKIP",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "setup_id": setup_id,
            "strategy_id": STRATEGY_ID,
            "source_strategy_id": SOURCE_STRATEGY_ID,
            "source_setup_id": source_setup_id,
            "symbol": symbol,
            "signal_timestamp": timestamp.isoformat(),
            "model_entry_price": model_entry,
            "bid": (quote or {}).get("bid"),
            "ask": (quote or {}).get("ask"),
            "spread_pct": (quote or {}).get("spread_pct"),
            "reason": reason,
        }
        self._append(row)
        self._write_status()

    def update(
        self, quotes: Mapping[str, Mapping[str, Any]], now: datetime
    ) -> list[dict[str, Any]]:
        """Advance open positions from executable bids and return new exits."""
        now = _utc(now)
        now_et = now.astimezone(NY)
        at_eod = (now_et.hour, now_et.minute) >= (self.eod_hour, self.eod_minute)
        closed = []
        changed = False

        for setup_id, record in list(self.active.items()):
            quote = quotes.get(str(record["symbol"]).upper()) or {}
            bid = _positive(quote.get("bid"))
            signal_day = _utc(record["signal_timestamp"]).astimezone(NY).date()

            if bid is None:
                if not (at_eod or now_et.date() > signal_day):
                    continue
                bid = _positive(record.get("last_bid"))
                if bid is None:
                    continue
            else:
                record["last_bid"] = bid
                record["last_bid_at"] = now.isoformat()
                changed = True

            if bid <= float(record["stop_price"]):
                reason = "STOP"
            elif bid >= float(record["target_price"]):
                reason = "TARGET"
            elif now_et.date() > signal_day or at_eod:
                reason = "EOD"
            elif nh015_should_exit(record, bid, now):
                reason = "NO_NEW_HIGH"
                changed = True
            else:
                continue

            return_pct = (bid / float(record["entry_price"]) - 1.0) * 100.0
            row = {
                **record,
                "event_type": "EXEC_EXIT",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "exit_timestamp": now.isoformat(),
                "exit_price": bid,
                "exit_bid": bid,
                "exit_reason": reason,
                "return_pct": return_pct,
            }
            self._append(row)
            closed.append(row)
            del self.active[setup_id]
            self.completed += 1
            changed = True

        if changed:
            self._persist()
        return closed
