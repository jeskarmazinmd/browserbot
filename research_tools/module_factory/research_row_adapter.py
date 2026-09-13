"""
Adapters into UnifiedResearchRow.

The old FeatureRow remains valid and untouched. This adapter lets
the new scientist layer consume it immediately, while richer
observation features can be merged when available.
"""

from __future__ import annotations

from typing import Mapping

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
    merge_ancestry_maps,
    merge_feature_maps,
)
from research_tools.module_factory.unified_catalog import (
    unified_catalog_by_name,
)


def _known_ancestry(
    features: Mapping[str, float],
) -> dict[str, tuple[str, ...]]:
    catalog = unified_catalog_by_name()

    return {
        name: (
            catalog[name].ancestry
            if name in catalog
            else ("DERIVED",)
        )
        for name in features
    }


def from_feature_row(
    row,
    *,
    extra_features: Mapping[
        str,
        float,
    ] | None = None,
    extra_ancestry: Mapping[
        str,
        tuple[str, ...],
    ] | None = None,
) -> UnifiedResearchRow:
    base_features = dict(
        row.features
    )

    extra_features = dict(
        extra_features or {}
    )

    base_ancestry = _known_ancestry(
        base_features
    )

    if extra_ancestry is None:
        extra_ancestry = _known_ancestry(
            extra_features
        )

    features = merge_feature_maps(
        base_features,
        extra_features,
    )

    ancestry = merge_ancestry_maps(
        base_ancestry,
        extra_ancestry,
    )

    return UnifiedResearchRow(
        symbol=row.symbol,
        minute=row.minute,
        price=float(row.price),
        features=features,
        forward_returns=dict(
            row.forward_returns
        ),
        feature_ancestry=ancestry,
    )
