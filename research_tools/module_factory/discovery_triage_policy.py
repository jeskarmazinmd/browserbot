"""
Dependence-aware shortlist policy for Module Factory discoveries.

This layer is intentionally conservative.

It does not freeze hypotheses and it does not access validation data.
It only ranks already-discovered candidates for possible inclusion in a
future validation batch.

Policy goals:
- reject exact semantic redundancies;
- require incremental evidence when a scientist claims incremental
  structure;
- preserve genuine sign-reversal lag discoveries;
- penalize weak independent-time support;
- prevent one broad concept from monopolizing the shortlist;
- enforce a hard shortlist ceiling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TriageCandidate:
    candidate_id: str
    scientist: str
    concept: str
    score: float
    independent_time_units: int = 100
    incremental_evidence: float | None = None
    sign_change: bool = False
    exact_redundant: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError(
                "candidate_id cannot be empty"
            )

        if not self.scientist:
            raise ValueError(
                "scientist cannot be empty"
            )

        if not self.concept:
            raise ValueError(
                "concept cannot be empty"
            )

        if not math.isfinite(
            float(self.score)
        ):
            raise ValueError(
                "score must be finite"
            )

        if self.independent_time_units < 0:
            raise ValueError(
                "independent_time_units "
                "cannot be negative"
            )

        if (
            self.incremental_evidence
            is not None
            and not math.isfinite(
                float(
                    self.incremental_evidence
                )
            )
        ):
            raise ValueError(
                "incremental_evidence "
                "must be finite"
            )


def _time_support_factor(
    independent_time_units: int,
) -> float:
    """
    Soft dependence penalty.

    100+ independent time units receives full weight.
    Smaller support receives sqrt scaling rather than a hard rejection.
    """

    if independent_time_units <= 0:
        return 0.0

    return min(
        1.0,
        math.sqrt(
            independent_time_units / 100.0
        ),
    )


def _adjusted_score(
    candidate: TriageCandidate,
) -> float:
    return (
        float(candidate.score)
        * _time_support_factor(
            candidate.independent_time_units
        )
    )


def _passes_incremental_gate(
    candidate: TriageCandidate,
    *,
    min_incremental_evidence: float,
) -> bool:
    """
    Incremental scientists should demonstrate incremental structure.

    A sign change is preserved because it represents a qualitatively
    different temporal relationship even when the scalar incremental
    magnitude is modest.
    """

    if candidate.incremental_evidence is None:
        return True

    if candidate.sign_change:
        return True

    return (
        float(
            candidate.incremental_evidence
        )
        >= min_incremental_evidence
    )


def select_diverse_candidates(
    candidates: list[TriageCandidate],
    *,
    max_candidates: int = 8,
    max_per_concept: int = 1,
    min_incremental_evidence: float = 0.02,
) -> list[TriageCandidate]:
    if max_candidates <= 0:
        raise ValueError(
            "max_candidates must be positive"
        )

    if max_per_concept <= 0:
        raise ValueError(
            "max_per_concept must be positive"
        )

    if min_incremental_evidence < 0:
        raise ValueError(
            "min_incremental_evidence "
            "cannot be negative"
        )

    eligible = []

    for candidate in candidates:
        if candidate.exact_redundant:
            continue

        if not _passes_incremental_gate(
            candidate,
            min_incremental_evidence=(
                min_incremental_evidence
            ),
        ):
            continue

        eligible.append(candidate)

    eligible.sort(
        key=lambda item: (
            _adjusted_score(item),
            float(item.score),
            item.candidate_id,
        ),
        reverse=True,
    )

    selected = []
    concept_counts: dict[str, int] = {}

    for candidate in eligible:
        count = concept_counts.get(
            candidate.concept,
            0,
        )

        if count >= max_per_concept:
            continue

        selected.append(candidate)

        concept_counts[
            candidate.concept
        ] = count + 1

        if len(selected) >= max_candidates:
            break

    return selected
