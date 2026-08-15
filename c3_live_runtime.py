"""Crash-safe runtime helpers for the C3 execution validator."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterable

from c3_live_logic import C3Logic, ExecutableQuote


class DurableC3:
    """Serialize state transitions and make the state snapshot authoritative."""

    def __init__(self, state_path: Path, ledger_path: Path, engine: C3Logic):
        self.state_path = Path(state_path)
        self.ledger_path = Path(ledger_path)
        self.engine = engine
        self.lock = threading.RLock()
        self.sequence = 0
        self.outbox: list[dict[str, Any]] = []
        self.ledger_sequence = 0

    @classmethod
    def load(cls, state_path: Path, ledger_path: Path, config=None) -> "DurableC3":
        state_path = Path(state_path)
        if not state_path.exists():
            return cls(state_path, ledger_path, C3Logic(config))
        payload = json.loads(state_path.read_text())
        runtime = cls(state_path, ledger_path, C3Logic.from_dict(payload["engine"], config))
        runtime.sequence = int(payload.get("sequence", 0))
        runtime.outbox = list(payload.get("outbox", []))
        if runtime.ledger_path.exists():
            for line in runtime.ledger_path.read_text().splitlines():
                try:
                    runtime.ledger_sequence = max(
                        runtime.ledger_sequence, int(json.loads(line).get("sequence", 0))
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        runtime._drain_outbox()
        return runtime

    @staticmethod
    def _atomic_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w") as handle:
            json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    def _write_state(self) -> None:
        self._atomic_json(self.state_path, {
            "runtime_version": 1,
            "sequence": self.sequence,
            "engine": self.engine.to_dict(),
            "outbox": self.outbox,
        })

    def _drain_outbox(self) -> None:
        publish = [row for row in self.outbox if int(row["sequence"]) > self.ledger_sequence]
        if publish:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a") as handle:
                for row in publish:
                    handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.ledger_sequence = int(publish[-1]["sequence"])
        if self.outbox:
            self.outbox = []
            self._write_state()

    def _commit(self, events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for event in events:
            self.sequence += 1
            rows.append({
                "sequence": self.sequence,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                **event,
            })

        # Persist events with the portfolio, then drain them to the ledger.
        # Sequence IDs make a crash during draining exactly-once on recovery.
        self.outbox.extend(rows)
        self._write_state()
        self._drain_outbox()
        return rows

    def register_signal(self, symbol: str, setup_id: str, target: float,
                        quote: ExecutableQuote) -> list[dict[str, Any]]:
        with self.lock:
            return self._commit(self.engine.register_signal(symbol, setup_id, target, quote))

    def on_quote(self, quote: ExecutableQuote, *, eod: bool = False) -> list[dict[str, Any]]:
        with self.lock:
            return self._commit(self.engine.on_quote(quote, eod=eod))


def snapshot_quote(snapshot: Any, observed_at: float) -> ExecutableQuote:
    """Convert the existing normalized Schwab snapshot without price fallback."""
    millis = lambda value: float(value) / 1000.0 if value is not None else None
    return ExecutableQuote(
        symbol=str(snapshot.symbol).upper(),
        observed_at=float(observed_at),
        bid=snapshot.bid,
        ask=snapshot.ask,
        last=snapshot.last,
        mark=snapshot.mark,
        quote_at=millis(snapshot.quote_time_ms),
        bid_at=millis(snapshot.bid_time_ms),
        ask_at=millis(snapshot.ask_time_ms),
        realtime=snapshot.realtime,
    )
