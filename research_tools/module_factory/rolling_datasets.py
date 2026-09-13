"""Immutable rolling discovery/validation roles and compact quote evidence."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import gzip
import json
import zlib
from pathlib import Path
from typing import Iterable


COMPACT_FIELDS = (
    "market_minute_utc", "symbol", "last", "bid", "ask",
    "bid_size_raw", "ask_size_raw", "quote_time_ms",
)


@dataclass(frozen=True)
class RollingDataset:
    day: str
    dataset_id: str
    role: str
    source_path: str
    compact_path: str
    assigned_at: str
    sealed: bool


class RollingDatasetLedger:
    def __init__(self, path: Path, *, discovery_days_per_validation: int = 4):
        self.path = Path(path)
        self.discovery_days_per_validation = max(1, int(discovery_days_per_validation))
        self._items: dict[str, RollingDataset] = {}
        if self.path.exists():
            payload = json.loads(self.path.read_text())
            stored = int(payload.get("discovery_days_per_validation", self.discovery_days_per_validation))
            if stored != self.discovery_days_per_validation:
                raise RuntimeError("rolling dataset cadence cannot change after assignment")
            self._items = {item["day"]: RollingDataset(**item) for item in payload.get("datasets", [])}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "version": 1,
            "discovery_days_per_validation": self.discovery_days_per_validation,
            "datasets": [asdict(self._items[key]) for key in sorted(self._items)],
        }, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def assign(self, day: str, *, source_path: Path, compact_path: Path) -> RollingDataset:
        parsed = date.fromisoformat(day)
        existing = self._items.get(day)
        if existing is not None:
            if existing.source_path != str(source_path) or existing.compact_path != str(compact_path):
                raise RuntimeError("dataset identity/path cannot mutate")
            return existing
        ordinal = len(self._items) + 1
        validation = ordinal % (self.discovery_days_per_validation + 1) == 0
        role = "VALIDATION" if validation else "DISCOVERY"
        item = RollingDataset(
            day=parsed.isoformat(), dataset_id=f"factory-market:{parsed.isoformat()}",
            role=role, source_path=str(source_path), compact_path=str(compact_path),
            assigned_at=datetime.now(timezone.utc).isoformat(), sealed=validation,
        )
        self._items[day] = item
        self._save()
        return item

    def datasets(self, role: str | None = None) -> tuple[RollingDataset, ...]:
        values = tuple(self._items[key] for key in sorted(self._items))
        return values if role is None else tuple(item for item in values if item.role == role)


def compact_rich_archive(source: Path, destination: Path) -> dict:
    """Write only fields needed by research/execution; never invent quotes."""
    source, destination = Path(source), Path(destination)
    if destination.exists() and destination.stat().st_size > 0:
        return {"created": False, "usable": True, "path": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    # A previous interrupted/corrupt attempt is never evidence of a sealed
    # dataset and must not be resumed as if it were complete.
    temporary.unlink(missing_ok=True)
    rows = 0
    try:
        with gzip.open(source, "rt", newline="") as src, gzip.open(temporary, "wt", newline="") as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=COMPACT_FIELDS)
            writer.writeheader()
            for row in reader:
                if not row.get("market_minute_utc") or not row.get("symbol"):
                    continue
                writer.writerow({name: row.get(name) for name in COMPACT_FIELDS})
                rows += 1
    except (EOFError, gzip.BadGzipFile, OSError, UnicodeError, zlib.error) as exc:
        temporary.unlink(missing_ok=True)
        return {
            "created": False,
            "usable": False,
            "path": str(destination),
            "source": str(source),
            "error": f"{type(exc).__name__}: {exc}",
        }
    temporary.replace(destination)
    return {"created": True, "usable": True, "path": str(destination), "rows": rows, "bytes": destination.stat().st_size}


def discover_completed_archives(root: Path, *, today: str | None = None) -> tuple[tuple[str, Path], ...]:
    today = today or datetime.now(timezone.utc).date().isoformat()
    found = []
    for path in Path(root).glob("minute_market_quotes_*.csv.gz"):
        compact = path.name.removeprefix("minute_market_quotes_").removesuffix(".csv.gz")
        if len(compact) != 8 or not compact.isdigit():
            continue
        day = f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        if day < today:
            found.append((day, path))
    return tuple(sorted(found))
