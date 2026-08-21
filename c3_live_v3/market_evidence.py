"""Compact prospective market evidence for research and replay."""

from __future__ import annotations

import csv
import gzip
from datetime import datetime, timezone
from pathlib import Path

from market_quotes import QuoteSnapshot


FIELDS = [
    "market_minute_utc",
    "observed_at_utc",
    "symbol",
    "legacy_price",
    "last",
    "mark",
    "bid",
    "ask",
    "last_size_raw",
    "bid_size_raw",
    "ask_size_raw",
    "quote_time_ms",
    "trade_time_ms",
    "bid_time_ms",
    "ask_time_ms",
    "regular_last",
    "regular_trade_time_ms",
    "extended_last",
    "last_mic",
    "bid_mic",
    "ask_mic",
    "realtime",
]


class MinuteMarketArchive:
    """Persist the final rich quote snapshot observed in each market minute."""

    def __init__(self, root, max_files=7):
        self.root=Path(root)
        self.max_files=int(max_files)
        self._minute=None
        self._observed_at=None
        self._snapshots=None
        self._eligible=False

    def update(self, observed_at, snapshots, regular_market_open):
        if observed_at.tzinfo is None:
            observed_at=observed_at.replace(tzinfo=timezone.utc)
        observed_at=observed_at.astimezone(timezone.utc)
        minute=observed_at.replace(second=0,microsecond=0)

        if self._minute is not None and minute != self._minute:
            self._flush_pending()

        if minute != self._minute:
            self._minute=minute
            self._snapshots=None
            self._observed_at=None
            self._eligible=False

        if regular_market_open:
            self._eligible=True
            self._observed_at=observed_at
            self._snapshots=dict(snapshots)

    def close(self):
        self._flush_pending()
        self._minute=None
        self._snapshots=None
        self._observed_at=None
        self._eligible=False

    def _path(self, minute):
        return self.root / (
            "minute_market_quotes_"
            + minute.strftime("%Y%m%d")
            + ".csv.gz"
        )

    def _flush_pending(self):
        if (
            not self._eligible
            or self._minute is None
            or self._observed_at is None
            or not self._snapshots
        ):
            return

        self.root.mkdir(parents=True,exist_ok=True)
        path=self._path(self._minute)
        new_file=not path.exists() or path.stat().st_size == 0

        with gzip.open(path,"at",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS)
            if new_file:
                writer.writeheader()

            for symbol in sorted(self._snapshots):
                snapshot=self._snapshots[symbol]
                if not isinstance(snapshot,QuoteSnapshot):
                    continue

                row=snapshot.as_dict()
                row.update({
                    "market_minute_utc":self._minute.isoformat(),
                    "observed_at_utc":self._observed_at.isoformat(),
                })
                writer.writerow({key:row.get(key) for key in FIELDS})

        self._prune()
        self._eligible=False
        self._snapshots=None

    def _prune(self):
        files=sorted(self.root.glob("minute_market_quotes_*.csv.gz"))
        while len(files) > self.max_files:
            oldest=files.pop(0)
            oldest.unlink(missing_ok=True)
