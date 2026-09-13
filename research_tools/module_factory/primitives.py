"""
Generic mathematical vocabulary for Module Factory.

This module deliberately contains no named trading strategies.

The factory observes measurable quantities, transforms them mathematically,
combines them into expressions, and asks whether those expressions contain
repeatable information about future returns.

Research only.  No trading-system imports.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Literal


Direction = Literal["low", "high"]


@dataclass(frozen=True)
class FeatureSpec:
    """One measurable quantity available to the discovery engine."""

    name: str
    family: str
    lookback: int | None = None
    transform: str = "identity"

    @property
    def feature_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:12].upper()


@dataclass(frozen=True)
class SignalSpec:
    """
    Generic one-dimensional hypothesis.

    Example:
        feature = return_5
        direction = low
        quantile = 0.10
        horizon = 20

    means only:

        "Do unusually low values of this observable predict future return?"

    It does NOT assume reversal.  The observed forward-return sign determines
    whether any economic relationship exists.
    """

    feature: FeatureSpec
    direction: Direction
    quantile: float
    horizon: int

    @property
    def signal_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return "SIG-" + hashlib.sha1(
            payload.encode()
        ).hexdigest()[:12].upper()


@dataclass(frozen=True)
class InteractionSpec:
    """Generic two-feature conditional hypothesis."""

    left: FeatureSpec
    left_direction: Direction
    left_quantile: float

    right: FeatureSpec
    right_direction: Direction
    right_quantile: float

    horizon: int

    @property
    def signal_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return "INT-" + hashlib.sha1(
            payload.encode()
        ).hexdigest()[:12].upper()


def base_feature_specs() -> list[FeatureSpec]:
    """
    Initial mathematical vocabulary.

    These are observables, not strategies.  More families can be added without
    changing the hypothesis/evaluation machinery.
    """

    specs: list[FeatureSpec] = []

    # Price displacement at multiple scales.
    for lookback in (1, 2, 3, 5, 10, 15, 20, 30, 60):
        specs.append(
            FeatureSpec(
                name=f"return_{lookback}",
                family="return",
                lookback=lookback,
            )
        )

    # Realized volatility.
    for lookback in (3, 5, 10, 20, 30, 60):
        specs.append(
            FeatureSpec(
                name=f"volatility_{lookback}",
                family="volatility",
                lookback=lookback,
            )
        )

    # Location within recent range.
    for lookback in (5, 10, 20, 30, 60):
        specs.append(
            FeatureSpec(
                name=f"range_position_{lookback}",
                family="range_position",
                lookback=lookback,
            )
        )

    # Trend persistence / sign balance.
    for lookback in (3, 5, 10, 20, 30):
        specs.append(
            FeatureSpec(
                name=f"up_fraction_{lookback}",
                family="sign_persistence",
                lookback=lookback,
            )
        )

    # First difference of returns: simple acceleration.
    for lookback in (2, 3, 5, 10, 20):
        specs.append(
            FeatureSpec(
                name=f"acceleration_{lookback}",
                family="acceleration",
                lookback=lookback,
            )
        )

    # Serial dependence.
    for lookback in (5, 10, 20, 30):
        specs.append(
            FeatureSpec(
                name=f"autocorr_1_{lookback}",
                family="autocorrelation",
                lookback=lookback,
            )
        )

    # Distribution shape.
    for lookback in (10, 20, 30, 60):
        specs.append(
            FeatureSpec(
                name=f"skew_{lookback}",
                family="distribution",
                lookback=lookback,
            )
        )
        specs.append(
            FeatureSpec(
                name=f"kurtosis_{lookback}",
                family="distribution",
                lookback=lookback,
            )
        )

    # Market-relative displacement.
    for lookback in (1, 3, 5, 10, 20, 30, 60):
        specs.append(
            FeatureSpec(
                name=f"spy_relative_return_{lookback}",
                family="relative_return",
                lookback=lookback,
            )
        )

    return specs


def generate_signal_specs(
    *,
    quantiles: tuple[float, ...] = (0.05, 0.10, 0.20),
    horizons: tuple[int, ...] = (1, 5, 10, 20),
) -> list[SignalSpec]:
    """Generate hypotheses mechanically from the mathematical vocabulary."""

    result: list[SignalSpec] = []

    for feature in base_feature_specs():
        for direction in ("low", "high"):
            for quantile in quantiles:
                for horizon in horizons:
                    result.append(
                        SignalSpec(
                            feature=feature,
                            direction=direction,
                            quantile=quantile,
                            horizon=horizon,
                        )
                    )

    return result


def generate_interaction_specs(
    *,
    quantile: float = 0.10,
    horizon: int = 20,
    max_features: int | None = None,
) -> list[InteractionSpec]:
    """
    Generate generic pairwise conditional hypotheses.

    Kept separate because pairwise search grows quadratically.
    """

    features = base_feature_specs()
    if max_features is not None:
        features = features[:max_features]

    result: list[InteractionSpec] = []

    for i, left in enumerate(features):
        for right in features[i + 1:]:
            for left_direction in ("low", "high"):
                for right_direction in ("low", "high"):
                    result.append(
                        InteractionSpec(
                            left=left,
                            left_direction=left_direction,
                            left_quantile=quantile,
                            right=right,
                            right_direction=right_direction,
                            right_quantile=quantile,
                            horizon=horizon,
                        )
                    )

    return result


def finite(value: float | None) -> bool:
    return (
        value is not None
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
