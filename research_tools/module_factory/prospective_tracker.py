"""Durable causal fixed-horizon tracking for Factory shadow modules.

Advances only from minutes actually processed by the Factory worker.
No feed read-ahead, no broker, no order placement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProspectiveObservation:
    key: str
    strategy_id: str
    symbol: str
    entry_timestamp: str
    entry_price: float
    direction: int
    horizon: int
    hypothesis_id: str
    specification_hash: str
    observed_minutes: int = 0
    last_observed_minute: str | None = None


@dataclass(frozen=True)
class ProspectiveOutcome:
    key: str
    strategy_id: str
    symbol: str
    entry_timestamp: str
    entry_price: float
    exit_timestamp: str
    exit_price: float
    direction: int
    horizon: int
    return_pct: float
    hypothesis_id: str
    specification_hash: str
    execution_model: str = "BIDASK_EXEC_V1"
    pricing: str = "LONG ask->bid; SHORT bid->ask"


class FactoryProspectiveTracker:
    def __init__(
        self,
        *,
        state_path: Path,
        outcomes_path: Path,
    ):
        self.state_path = Path(state_path)
        self.outcomes_path = Path(outcomes_path)
        self._active: dict[str, ProspectiveObservation] = {}
        self._completed_keys: set[str] = set()
        self._journal_offset = 0
        self._load()

    @staticmethod
    def signal_key(
        *,
        strategy_id: str,
        symbol: str,
        timestamp: Any,
    ) -> str:
        return (
            f"{strategy_id}|{symbol}|"
            f"{_parse_timestamp(timestamp).isoformat()}"
        )

    def _load(self) -> None:
        if self.state_path.exists():
            payload = json.loads(self.state_path.read_text())

            if payload.get("version") not in (1, 2):
                raise RuntimeError(
                    "unsupported Factory prospective tracker state version"
                )

            for item in payload.get("active", []):
                item = dict(item)
                item.pop("entry_minute", None)
                item.setdefault("observed_minutes", 0)
                item.setdefault("last_observed_minute", None)

                observation = ProspectiveObservation(**item)
                self._active[observation.key] = observation
            self._journal_offset = max(0, int(payload.get("journal_offset", 0)))

        if self.outcomes_path.exists():
            with self.outcomes_path.open() as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    key = item.get("key")
                    if key:
                        self._completed_keys.add(str(key))
        # Outcome append precedes active-state removal.  If power is lost in
        # that gap, the durable outcome wins and must not be emitted twice.
        for key in self._completed_keys:
            self._active.pop(key, None)

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                {
                    "version": 2,
                    "active": [
                        asdict(item)
                        for item in sorted(
                            self._active.values(),
                            key=lambda row: row.key,
                        )
                    ],
                    "journal_offset": self._journal_offset,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        temporary.replace(self.state_path)

    def _append_outcome(
        self,
        outcome: ProspectiveOutcome,
    ) -> None:
        self.outcomes_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.outcomes_path.open("a") as handle:
            handle.write(
                json.dumps(
                    asdict(outcome),
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    def reconcile_signal_journal(self, signal_path: Path, quote_feed: Any) -> dict[str, int]:
        """Enroll every complete durable signal record exactly once.

        Offset advancement is committed after each record.  Enrollment itself
        is idempotent, so either ordering is safe across an immediate crash.
        A truncated final record is retried after the next append.
        """
        path = Path(signal_path)
        result = {"records": 0, "enrolled": 0, "rejected": 0}
        if not path.exists():
            return result
        size = path.stat().st_size
        if self._journal_offset > size:
            self._journal_offset = 0
        with path.open("rb") as handle:
            handle.seek(self._journal_offset)
            while True:
                start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    handle.seek(start)
                    break
                end = handle.tell()
                try:
                    row = json.loads(raw)
                    direction = int(row["direction"])
                    entry = quote_feed.entry_price(
                        timestamp=row["timestamp"], symbol=row["symbol"],
                        direction=direction,
                    )
                    data = row.get("data") or {}
                    accepted = entry is not None and self.observe_signal(
                        strategy_id=row["strategy_id"], symbol=row["symbol"],
                        timestamp=row["timestamp"], entry_price=entry,
                        direction=direction, horizon=int(row["horizon"]),
                        hypothesis_id=str(data["hypothesis_id"]),
                        specification_hash=str(data["specification_hash"]),
                    )
                    result["enrolled" if accepted else "rejected"] += 1
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    result["rejected"] += 1
                result["records"] += 1
                self._journal_offset = end
                self._save_state()
        return result

    def observe_signal(
        self,
        *,
        strategy_id: str,
        symbol: str,
        timestamp: Any,
        entry_price: Any,
        direction: int,
        horizon: int,
        hypothesis_id: str,
        specification_hash: str,
    ) -> bool:
        price = _finite_positive(entry_price)
        if price is None:
            return False

        if direction not in (-1, 1):
            return False

        if int(horizon) <= 0:
            return False

        timestamp_iso = _parse_timestamp(timestamp).isoformat()

        key = self.signal_key(
            strategy_id=strategy_id,
            symbol=symbol,
            timestamp=timestamp_iso,
        )

        if key in self._completed_keys or key in self._active:
            return False

        self._active[key] = ProspectiveObservation(
            key=key,
            strategy_id=str(strategy_id),
            symbol=str(symbol),
            entry_timestamp=timestamp_iso,
            entry_price=price,
            direction=int(direction),
            horizon=int(horizon),
            hypothesis_id=str(hypothesis_id),
            specification_hash=str(specification_hash),
        )

        self._save_state()
        return True

    def consume_minute(
        self,
        timestamp: Any,
        prices: Mapping[str, float],
    ) -> tuple[ProspectiveOutcome, ...]:
        """Advance observations by exactly one processed tape minute."""

        minute = _parse_timestamp(timestamp)
        minute_iso = minute.isoformat()

        completed = []
        changed = False

        for key, observation in list(self._active.items()):
            entry_time = _parse_timestamp(
                observation.entry_timestamp
            )

            if minute <= entry_time:
                continue

            if (
                observation.last_observed_minute is not None
                and minute
                <= _parse_timestamp(
                    observation.last_observed_minute
                )
            ):
                continue

            price = _finite_positive(
                prices.get(observation.symbol)
            )
            if price is None:
                continue

            observed_minutes = observation.observed_minutes + 1

            if observed_minutes < observation.horizon:
                self._active[key] = ProspectiveObservation(
                    **{
                        **asdict(observation),
                        "observed_minutes": observed_minutes,
                        "last_observed_minute": minute_iso,
                    }
                )
                changed = True
                continue

            raw_return = (
                price / observation.entry_price - 1.0
            ) * 100.0

            paper_return = (
                observation.direction * raw_return
            )

            outcome = ProspectiveOutcome(
                key=observation.key,
                strategy_id=observation.strategy_id,
                symbol=observation.symbol,
                entry_timestamp=observation.entry_timestamp,
                entry_price=observation.entry_price,
                exit_timestamp=minute_iso,
                exit_price=price,
                direction=observation.direction,
                horizon=observation.horizon,
                return_pct=paper_return,
                hypothesis_id=observation.hypothesis_id,
                specification_hash=observation.specification_hash,
            )

            self._append_outcome(outcome)
            self._completed_keys.add(key)
            del self._active[key]

            completed.append(outcome)
            changed = True

        if changed:
            self._save_state()

        return tuple(completed)

    def consume_executable_minute(
        self,
        timestamp: Any,
        quotes: Mapping[str, Any],
    ) -> tuple[ProspectiveOutcome, ...]:
        """Advance using executable exit sides; missing quotes fail closed."""
        prices: dict[str, float] = {}
        for observation in self._active.values():
            quote = quotes.get(observation.symbol)
            if quote is None:
                continue
            try:
                price = quote.exit_price(observation.direction)
            except (AttributeError, TypeError, ValueError):
                continue
            valid = _finite_positive(price)
            if valid is not None:
                prices[observation.symbol] = valid
        return self.consume_minute(timestamp, prices)

    @property
    def active_count(self) -> int:
        return len(self._active)
