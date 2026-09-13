"""
Unified feature metadata catalog.

This joins the existing price/market vocabulary with the generic
microstructure vocabulary behind one metadata interface.

No signal direction, threshold, or expected return is represented.
"""

from __future__ import annotations

from research_tools.module_factory.feature_catalog import (
    microstructure_catalog,
)
from research_tools.module_factory.primitives import (
    base_feature_specs,
)
from research_tools.module_factory.research_rows import (
    ResearchFeatureMeta,
)


def price_feature_catalog(
) -> tuple[ResearchFeatureMeta, ...]:
    features = []

    for spec in (
        base_feature_specs()
    ):
        ancestry = (
            ("PRICE", "MARKET_CONTEXT")
            if spec.family
            == "relative_return"
            else ("PRICE",)
        )

        features.append(
            ResearchFeatureMeta(
                name=spec.name,
                family=spec.family,
                source="price_history",
                temporal=True,
                ancestry=ancestry,
            )
        )

    return tuple(features)


def observation_feature_catalog(
) -> tuple[ResearchFeatureMeta, ...]:
    return tuple(
        ResearchFeatureMeta(
            name=feature.name,
            family=feature.family,
            source=feature.source,
            temporal=feature.temporal,
            ancestry=feature.ancestry,
        )
        for feature
        in microstructure_catalog()
    )


def unified_feature_catalog(
) -> tuple[ResearchFeatureMeta, ...]:
    combined = (
        price_feature_catalog()
        + observation_feature_catalog()
    )

    names = [
        feature.name
        for feature in combined
    ]

    if len(names) != len(set(names)):
        duplicates = sorted({
            name
            for name in names
            if names.count(name) > 1
        })

        raise ValueError(
            "unified feature-name collision: "
            + ", ".join(duplicates)
        )

    return combined


def unified_catalog_by_name(
) -> dict[str, ResearchFeatureMeta]:
    return {
        feature.name: feature
        for feature
        in unified_feature_catalog()
    }


def ancestry_map(
) -> dict[str, tuple[str, ...]]:
    return {
        feature.name: feature.ancestry
        for feature
        in unified_feature_catalog()
    }


def features_by_ancestry(
    ancestry: str,
) -> tuple[str, ...]:
    return tuple(
        feature.name
        for feature
        in unified_feature_catalog()
        if ancestry in feature.ancestry
    )
