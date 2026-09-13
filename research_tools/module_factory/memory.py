"""
Persistent experiment memory for Module Factory.

Every mathematical hypothesis tested by the factory can be remembered,
including failures.

This prevents:
- rediscovering identical dead ideas
- treating repeated tests as independent discoveries
- losing lineage
- forgetting why candidates were rejected

JSONL is used initially because it is append-friendly, inspectable, and
consistent with the rest of the repository.  Storage can move to SQLite
later without changing experiment identities.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


STATUSES = {
    "GENERATED",
    "TESTED",
    "HISTORICAL_PASS",
    "HISTORICAL_REJECT",
    "SHADOW_ENABLED",
    "SHADOW_WATCH",
    "SHADOW_DISABLED",
    "PROSPECTIVE_PASS",
    "LIVE_ELIGIBLE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def experiment_id(
    feature: str,
    horizon: int,
) -> str:
    payload = json.dumps(
        {
            "feature": feature,
            "horizon": int(horizon),
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    return "MF-" + hashlib.sha1(
        payload.encode()
    ).hexdigest()[:14].upper()


@dataclass
class ExperimentRecord:
    experiment_id: str
    feature: str
    horizon: int
    generation: int
    lineage: tuple[str, ...]
    status: str

    created_at_utc: str
    updated_at_utc: str

    test_count: int = 0
    discovery_score: float | None = None
    search_score: float | None = None
    bh_pass: bool | None = None
    sign_consistency: float | None = None
    worst_day_edge: float | None = None
    observations: int | None = None

    rejection_reason: str | None = None
    metadata: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(
                f"invalid experiment status: {self.status}"
            )

        expected = experiment_id(
            self.feature,
            self.horizon,
        )

        if self.experiment_id != expected:
            raise ValueError(
                "experiment_id does not match "
                "feature/horizon specification"
            )


class ExperimentMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.records: dict[str, ExperimentRecord] = {}
        self._load()

    def _load(self) -> None:
        self.records = {}

        if not self.path.exists():
            return

        with self.path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                raw = json.loads(line)

                raw["lineage"] = tuple(
                    raw.get("lineage") or ()
                )

                record = ExperimentRecord(**raw)
                record.validate()

                # JSONL is an event/update log.
                # Last record for an ID is current state.
                self.records[
                    record.experiment_id
                ] = record

    def __len__(self) -> int:
        return len(self.records)

    def get(
        self,
        feature: str,
        horizon: int,
    ) -> ExperimentRecord | None:
        return self.records.get(
            experiment_id(feature, horizon)
        )

    def seen(
        self,
        feature: str,
        horizon: int,
    ) -> bool:
        return self.get(feature, horizon) is not None

    def current(
        self,
    ) -> list[ExperimentRecord]:
        return sorted(
            self.records.values(),
            key=lambda x: x.experiment_id,
        )

    def append(
        self,
        record: ExperimentRecord,
    ) -> ExperimentRecord:
        record.validate()

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    asdict(record),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

        self.records[
            record.experiment_id
        ] = record

        return record

    def create(
        self,
        *,
        feature: str,
        horizon: int,
        generation: int,
        lineage: Iterable[str],
        status: str = "GENERATED",
        metadata: dict | None = None,
    ) -> ExperimentRecord:

        existing = self.get(
            feature,
            horizon,
        )

        if existing is not None:
            return existing

        now = utc_now()

        return self.append(
            ExperimentRecord(
                experiment_id=experiment_id(
                    feature,
                    horizon,
                ),
                feature=feature,
                horizon=horizon,
                generation=generation,
                lineage=tuple(lineage),
                status=status,
                created_at_utc=now,
                updated_at_utc=now,
                metadata=dict(metadata or {}),
            )
        )

    def update(
        self,
        record: ExperimentRecord,
        *,
        status: str | None = None,
        **changes,
    ) -> ExperimentRecord:

        data = asdict(record)

        if status is not None:
            data["status"] = status

        data.update(changes)
        data["updated_at_utc"] = utc_now()
        data["lineage"] = tuple(data["lineage"])

        updated = ExperimentRecord(**data)
        return self.append(updated)

    def untested(
        self,
        specifications: Iterable[
            tuple[str, int]
        ],
    ) -> list[tuple[str, int]]:

        return [
            (feature, horizon)
            for feature, horizon
            in specifications
            if not self.seen(
                feature,
                horizon,
            )
        ]


def record_candidate_result(
    memory: ExperimentMemory,
    *,
    feature: str,
    horizon: int,
    generation: int,
    lineage: Iterable[str],
    discovery_score: float,
    search_score: float,
    bh_pass: bool,
    sign_consistency: float,
    worst_day_edge: float,
    observations: int,
    selected: bool,
    rejection_reason: str | None = None,
    metadata: dict | None = None,
) -> ExperimentRecord:

    record = memory.create(
        feature=feature,
        horizon=horizon,
        generation=generation,
        lineage=lineage,
        metadata=metadata,
    )

    status = (
        "HISTORICAL_PASS"
        if selected
        else "HISTORICAL_REJECT"
    )

    return memory.update(
        record,
        status=status,
        test_count=record.test_count + 1,
        discovery_score=discovery_score,
        search_score=search_score,
        bh_pass=bh_pass,
        sign_consistency=sign_consistency,
        worst_day_edge=worst_day_edge,
        observations=observations,
        rejection_reason=(
            None
            if selected
            else rejection_reason
        ),
    )
