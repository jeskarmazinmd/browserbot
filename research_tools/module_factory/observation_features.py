"""
Generic observation-feature layer for Module Factory.

This module turns provider-independent MarketObservation objects
into mathematical variables available to the research system.

It deliberately separates:

    raw provider data
        -> MarketObservation
        -> generic observation features
        -> scientists / expressions / hypotheses

No predictive direction is encoded here.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable

from research_tools.module_factory.market_observations import (
    MarketObservation,
)
from research_tools.module_factory.microstructure_features import (
    derive_microstructure_features,
)


MICROSTRUCTURE_BASE_FEATURES = (
    "spread_bps",
    "depth_imbalance",
    "microprice_displacement_bps",
    "last_vs_mid_bps",
    "mark_vs_mid_bps",
    "quote_age_ms",
    "trade_age_ms",
    "side_age_imbalance_ms",
    "quote_trade_age_gap_ms",
    "last_size_share",
    "bid_ask_same_venue",
    "trade_bid_same_venue",
    "trade_ask_same_venue",
)

TEMPORAL_MICROSTRUCTURE_FEATURES = (
    "spread_bps_change",
    "depth_imbalance_change",
    "microprice_displacement_bps_change",
    "last_vs_mid_bps_change",
    "quote_age_ms_change",
    "trade_age_ms_change",
)

ROLLING_MICROSTRUCTURE_BASES = (
    "spread_bps",
    "depth_imbalance",
    "microprice_displacement_bps",
    "last_vs_mid_bps",
    "quote_age_ms",
    "trade_age_ms",
)

ROLLING_WINDOWS = (
    3,
    5,
    10,
)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _mean(values: list[float]) -> float:
    finite = [
        value
        for value in values
        if _finite(value)
    ]

    if not finite:
        return math.nan

    return sum(finite) / len(finite)


def _std(values: list[float]) -> float:
    finite = [
        value
        for value in values
        if _finite(value)
    ]

    if len(finite) < 2:
        return math.nan

    mean = sum(finite) / len(finite)

    variance = sum(
        (value - mean) ** 2
        for value in finite
    ) / len(finite)

    return math.sqrt(variance)


def base_microstructure_dict(
    observation: MarketObservation,
) -> dict[str, float]:
    features = derive_microstructure_features(
        observation
    )

    return {
        name: float(
            getattr(features, name)
        )
        for name
        in MICROSTRUCTURE_BASE_FEATURES
    }


def generic_microstructure_feature_names(
) -> tuple[str, ...]:
    names = list(
        MICROSTRUCTURE_BASE_FEATURES
    )

    names.extend(
        TEMPORAL_MICROSTRUCTURE_FEATURES
    )

    for base in (
        ROLLING_MICROSTRUCTURE_BASES
    ):
        for window in ROLLING_WINDOWS:
            names.append(
                f"{base}_mean_{window}"
            )
            names.append(
                f"{base}_std_{window}"
            )

    return tuple(names)


@dataclass
class ObservationFeatureState:
    """
    Stateful temporal transformer.

    State is maintained independently by symbol so observations
    from different securities cannot contaminate one another.
    """

    max_history: int = 10
    _history: dict[
        str,
        deque[dict[str, float]],
    ] = field(
        default_factory=lambda: defaultdict(
            lambda: deque(maxlen=10)
        )
    )

    def __post_init__(self):
        if self.max_history < max(
            ROLLING_WINDOWS
        ):
            raise ValueError(
                "max_history must cover "
                "largest rolling window"
            )

        # defaultdict factory must reflect custom max_history.
        self._history = defaultdict(
            lambda: deque(
                maxlen=self.max_history
            )
        )

    def transform(
        self,
        observation: MarketObservation,
    ) -> dict[str, float]:
        current = base_microstructure_dict(
            observation
        )

        history = self._history[
            observation.symbol
        ]

        output = dict(current)

        previous = (
            history[-1]
            if history
            else None
        )

        change_map = {
            "spread_bps_change":
                "spread_bps",
            "depth_imbalance_change":
                "depth_imbalance",
            "microprice_displacement_bps_change":
                "microprice_displacement_bps",
            "last_vs_mid_bps_change":
                "last_vs_mid_bps",
            "quote_age_ms_change":
                "quote_age_ms",
            "trade_age_ms_change":
                "trade_age_ms",
        }

        for output_name, base_name in (
            change_map.items()
        ):
            current_value = current[
                base_name
            ]

            if previous is None:
                output[output_name] = (
                    math.nan
                )
                continue

            previous_value = previous[
                base_name
            ]

            if (
                _finite(current_value)
                and _finite(previous_value)
            ):
                output[output_name] = (
                    current_value
                    - previous_value
                )
            else:
                output[output_name] = (
                    math.nan
                )

        combined = (
            list(history)
            + [current]
        )

        for base in (
            ROLLING_MICROSTRUCTURE_BASES
        ):
            for window in ROLLING_WINDOWS:
                if len(combined) < window:
                    values = []
                else:
                    values = [
                        row[base]
                        for row
                        in combined[-window:]
                    ]

                output[
                    f"{base}_mean_{window}"
                ] = _mean(values)

                output[
                    f"{base}_std_{window}"
                ] = _std(values)

        history.append(current)

        return output


def build_observation_feature_rows(
    observations: Iterable[
        MarketObservation
    ],
) -> list[
    tuple[
        MarketObservation,
        dict[str, float],
    ]
]:
    """
    Build generic feature rows in supplied observation order.

    Caller remains responsible for chronological ordering.
    """

    state = ObservationFeatureState()

    rows = []

    for observation in observations:
        rows.append(
            (
                observation,
                state.transform(
                    observation
                ),
            )
        )

    return rows
