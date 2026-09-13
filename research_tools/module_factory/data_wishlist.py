"""
Persistent data wishlist for Module Factory.

Blocked and degraded research ideas are retained and aggregated
by missing information capability.

The goal is to answer:

    "What additional data would unlock the most valuable
     currently inaccessible research?"

rather than buying data based on intuition alone.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from research_tools.module_factory.data_capabilities import (
    TestabilityAssessment,
)
from research_tools.module_factory.idea_library import (
    ResearchIdea,
)


@dataclass(frozen=True)
class WishlistEntry:
    capability: str
    idea_id: str
    concept: str
    source_type: str
    testability_status: str
    fidelity: float
    novelty: float
    confidence_prior: float
    importance: float
    reason: str


@dataclass(frozen=True)
class CapabilityDemand:
    capability: str
    ideas: int
    concepts: int
    source_types: int
    blocked_ideas: int
    partial_ideas: int
    mean_importance: float
    total_importance: float


def idea_importance(
    idea: ResearchIdea,
    assessment: TestabilityAssessment,
) -> float:
    """
    Research-priority score, NOT expected trading return.

    Higher novelty and prior intellectual support increase the
    value of unlocking an idea. Existing fidelity reduces the
    incremental value of acquiring missing data.
    """

    base = (
        0.45
        + 0.35 * idea.novelty
        + 0.20 * idea.confidence_prior
    )

    information_gap = (
        1.0 - assessment.fidelity
    )

    blocked_bonus = (
        1.20
        if assessment.status == "BLOCKED"
        else 1.0
    )

    return round(
        base
        * (
            0.35
            + 0.65 * information_gap
        )
        * blocked_bonus,
        6,
    )


def entries_for_idea(
    idea: ResearchIdea,
    assessment: TestabilityAssessment,
) -> list[WishlistEntry]:
    if assessment.status == "FULLY_TESTABLE":
        return []

    importance = idea_importance(
        idea,
        assessment,
    )

    entries = []

    for capability in (
        assessment.missing_required
    ):
        entries.append(
            WishlistEntry(
                capability=capability,
                idea_id=idea.idea_id,
                concept=idea.concept,
                source_type=(
                    idea.source.source_type
                ),
                testability_status=(
                    assessment.status
                ),
                fidelity=assessment.fidelity,
                novelty=idea.novelty,
                confidence_prior=(
                    idea.confidence_prior
                ),
                importance=importance,
                reason=(
                    "Required capability missing."
                ),
            )
        )

    # If an intended capability is being approximated by a
    # substitute, retaining it on the wishlist allows us to
    # measure demand for higher-fidelity data.
    for substitution in (
        assessment.substituted
    ):
        capability = substitution.split(
            "<-",
            1,
        )[0]

        entries.append(
            WishlistEntry(
                capability=capability,
                idea_id=idea.idea_id,
                concept=idea.concept,
                source_type=(
                    idea.source.source_type
                ),
                testability_status=(
                    assessment.status
                ),
                fidelity=assessment.fidelity,
                novelty=idea.novelty,
                confidence_prior=(
                    idea.confidence_prior
                ),
                importance=round(
                    importance * 0.6,
                    6,
                ),
                reason=(
                    f"Currently approximated: "
                    f"{substitution}"
                ),
            )
        )

    return entries


class DataWishlist:
    def __init__(
        self,
        path: str | Path | None = None,
    ):
        self.path = (
            Path(path)
            if path is not None
            else None
        )

        self._entries: dict[
            tuple[str, str],
            WishlistEntry,
        ] = {}

        if (
            self.path is not None
            and self.path.exists()
        ):
            self._load()

    def _load(self) -> None:
        with self.path.open() as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                payload = json.loads(line)

                entry = WishlistEntry(
                    capability=payload[
                        "capability"
                    ],
                    idea_id=payload[
                        "idea_id"
                    ],
                    concept=payload[
                        "concept"
                    ],
                    source_type=payload[
                        "source_type"
                    ],
                    testability_status=payload[
                        "testability_status"
                    ],
                    fidelity=float(
                        payload["fidelity"]
                    ),
                    novelty=float(
                        payload["novelty"]
                    ),
                    confidence_prior=float(
                        payload[
                            "confidence_prior"
                        ]
                    ),
                    importance=float(
                        payload["importance"]
                    ),
                    reason=payload["reason"],
                )

                self._entries[
                    (
                        entry.capability,
                        entry.idea_id,
                    )
                ] = entry

    def add(
        self,
        entry: WishlistEntry,
    ) -> None:
        key = (
            entry.capability,
            entry.idea_id,
        )

        self._entries[key] = entry

        if self.path is not None:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.path.open(
                "a"
            ) as handle:
                handle.write(
                    json.dumps(
                        asdict(entry),
                        sort_keys=True,
                    )
                    + "\n"
                )

    def add_many(
        self,
        entries: Iterable[
            WishlistEntry
        ],
    ) -> None:
        for entry in entries:
            self.add(entry)

    def current(
        self,
    ) -> list[WishlistEntry]:
        return list(
            self._entries.values()
        )

    def rank_capabilities(
        self,
    ) -> list[CapabilityDemand]:
        grouped = {}

        for entry in self.current():
            grouped.setdefault(
                entry.capability,
                [],
            ).append(entry)

        results = []

        for capability, entries in (
            grouped.items()
        ):
            total = sum(
                entry.importance
                for entry in entries
            )

            results.append(
                CapabilityDemand(
                    capability=capability,
                    ideas=len({
                        entry.idea_id
                        for entry in entries
                    }),
                    concepts=len({
                        entry.concept
                        for entry in entries
                    }),
                    source_types=len({
                        entry.source_type
                        for entry in entries
                    }),
                    blocked_ideas=sum(
                        entry.testability_status
                        == "BLOCKED"
                        for entry in entries
                    ),
                    partial_ideas=sum(
                        entry.testability_status
                        == "PARTIALLY_TESTABLE"
                        for entry in entries
                    ),
                    mean_importance=round(
                        total / len(entries),
                        6,
                    ),
                    total_importance=round(
                        total,
                        6,
                    ),
                )
            )

        return sorted(
            results,
            key=lambda item: (
                -item.total_importance,
                -item.ideas,
                item.capability,
            ),
        )

    def __len__(self) -> int:
        return len(self._entries)
