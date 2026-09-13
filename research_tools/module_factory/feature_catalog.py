"""
Unified mathematical feature catalog for Module Factory.

The catalog describes what variables scientists are allowed to
reason about. It contains no predictive direction or trading rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from research_tools.module_factory.observation_features import (
    MICROSTRUCTURE_BASE_FEATURES,
    ROLLING_MICROSTRUCTURE_BASES,
    ROLLING_WINDOWS,
    TEMPORAL_MICROSTRUCTURE_FEATURES,
)


@dataclass(frozen=True)
class CatalogFeature:
    name: str
    family: str
    source: str
    temporal: bool
    ancestry: tuple[str, ...]


def microstructure_catalog(
) -> tuple[CatalogFeature, ...]:
    features = []

    for name in (
        MICROSTRUCTURE_BASE_FEATURES
    ):
        features.append(
            CatalogFeature(
                name=name,
                family="microstructure",
                source="observation",
                temporal=False,
                ancestry=(
                    "LEVEL1_SNAPSHOT",
                ),
            )
        )

    for name in (
        TEMPORAL_MICROSTRUCTURE_FEATURES
    ):
        features.append(
            CatalogFeature(
                name=name,
                family=(
                    "microstructure_change"
                ),
                source="observation_history",
                temporal=True,
                ancestry=(
                    "LEVEL1_SNAPSHOT",
                    "TEMPORAL",
                ),
            )
        )

    for base in (
        ROLLING_MICROSTRUCTURE_BASES
    ):
        for window in ROLLING_WINDOWS:
            for statistic in (
                "mean",
                "std",
            ):
                features.append(
                    CatalogFeature(
                        name=(
                            f"{base}_"
                            f"{statistic}_"
                            f"{window}"
                        ),
                        family=(
                            "microstructure_rolling"
                        ),
                        source=(
                            "observation_history"
                        ),
                        temporal=True,
                        ancestry=(
                            "LEVEL1_SNAPSHOT",
                            "TEMPORAL",
                        ),
                    )
                )

    return tuple(features)


def catalog_by_name(
) -> dict[str, CatalogFeature]:
    return {
        feature.name: feature
        for feature
        in microstructure_catalog()
    }
