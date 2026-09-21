"""Atomic cross-process publication of the collector's latest rich L1 quotes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

from market_quotes import QuoteSnapshot


SCHEMA = "LIVE_L1_V1"
DEFAULT_PATH = Path(os.environ.get("LIVE_L1_SNAPSHOT_PATH", "/data/live_l1_snapshot.json"))


def publish_live_l1_snapshot(
    snapshots: Mapping[str, QuoteSnapshot],
    observed_at: datetime,
    path: Path | str = DEFAULT_PATH,
) -> None:
    """Publish one complete collector cycle using same-directory atomic replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    observed_at = observed_at.astimezone(timezone.utc)
    observed_text = observed_at.isoformat()
    quotes = {}
    for symbol, snapshot in snapshots.items():
        record = snapshot.as_dict()
        record["symbol"] = str(symbol).upper()
        record["collector_observed_at"] = observed_text
        quotes[record["symbol"]] = record

    payload = {
        "schema": SCHEMA,
        "collector_observed_at": observed_text,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "quote_count": len(quotes),
        "quotes": quotes,
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w") as handle:
            json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LiveL1SnapshotReader:
    """Read complete snapshots and reuse a parsed cycle until it is replaced."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._identity = None
        self._quotes = {}
        self._collector_observed_at = None

    @property
    def collector_observed_at(self):
        self._refresh()
        return self._collector_observed_at

    def _refresh(self) -> None:
        try:
            stat = self.path.stat()
            identity = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            if identity == self._identity:
                return
            payload = json.loads(self.path.read_text())
            if payload.get("schema") != SCHEMA:
                raise ValueError("unsupported live L1 snapshot schema")
            quotes = payload.get("quotes")
            if not isinstance(quotes, dict):
                raise ValueError("live L1 snapshot quotes must be an object")
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            # Fail closed. Do not keep using an older cycle after the path has
            # disappeared or become unreadable.
            self._identity = None
            self._quotes = {}
            self._collector_observed_at = None
            return

        self._identity = identity
        self._collector_observed_at = payload.get("collector_observed_at")
        self._quotes = {
            str(symbol).upper(): dict(quote)
            for symbol, quote in quotes.items()
            if symbol and isinstance(quote, dict)
        }

    def quotes(self, symbols: Iterable[str]) -> dict:
        self._refresh()
        requested = dict.fromkeys(
            str(symbol).upper() for symbol in symbols if symbol
        )
        return {
            symbol: self._quotes[symbol]
            for symbol in requested
            if symbol in self._quotes
        }
