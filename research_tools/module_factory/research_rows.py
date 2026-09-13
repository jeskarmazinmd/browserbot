"""
Unified research-row interface for Module Factory.

Scientists should consume one mathematical interface regardless of
where a variable originated:

    price history
    market-relative history
    Level-1 microstructure
    temporal microstructure
    future targets

The interface deliberately preserves feature ancestry and does not
encode predictive direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ResearchFeatureMeta:
    name: str
    family: str
    source: str
    temporal: bool = False
    ancestry: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class UnifiedResearchRow:
    symbol: str
    minute: object
    price: float
    features: Mapping[str, float]
    forward_returns: Mapping[int, float]
    feature_ancestry: Mapping[
        str,
        tuple[str, ...],
    ] = field(default_factory=dict)

    def feature(
        self,
        name: str,
    ) -> float:
        value = self.features.get(
            name,
            math.nan,
        )

        try:
            return float(value)
        except (TypeError, ValueError):
            return math.nan

    def outcome(
        self,
        horizon: int,
    ) -> float:
        value = self.forward_returns.get(
            horizon,
            math.nan,
        )

        try:
            return float(value)
        except (TypeError, ValueError):
            return math.nan

    def ancestry(
        self,
        name: str,
    ) -> tuple[str, ...]:
        return tuple(
            self.feature_ancestry.get(
                name,
                (),
            )
        )


def merge_feature_maps(
    *feature_maps: Mapping[str, float],
) -> dict[str, float]:
    """
    Merge feature families while refusing silent name collisions.
    """

    merged: dict[str, float] = {}

    for feature_map in feature_maps:
        for name, value in feature_map.items():
            if name in merged:
                raise ValueError(
                    "feature collision: "
                    f"{name}"
                )

            merged[name] = value

    return merged


def merge_ancestry_maps(
    *ancestry_maps: Mapping[
        str,
        tuple[str, ...],
    ],
) -> dict[str, tuple[str, ...]]:
    merged = {}

    for ancestry_map in ancestry_maps:
        for name, ancestry in (
            ancestry_map.items()
        ):
            if name in merged:
                raise ValueError(
                    "ancestry collision: "
                    f"{name}"
                )

            merged[name] = tuple(
                ancestry
            )

    return merged


def feature_names(
    rows: Iterable[
        UnifiedResearchRow
    ],
) -> tuple[str, ...]:
    names = set()

    for row in rows:
        names.update(
            row.features.keys()
        )

    return tuple(sorted(names))
