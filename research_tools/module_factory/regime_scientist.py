"""
Regime scientist for Module Factory.

Question:
    Does the relationship between a feature and a future outcome
    materially change across states of another feature?

It can identify:
    - relationships that exist primarily in one regime
    - large changes in predictive strength
    - empirical sign reversals between regimes

Regimes are defined mechanically from the observed distribution.
No predictive direction is specified in advance.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
        return math.nan

    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)

    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]

    vx = sum(x * x for x in dx)
    vy = sum(y * y for y in dy)

    if vx <= 1e-18 or vy <= 1e-18:
        return math.nan

    return sum(
        x * y
        for x, y in zip(dx, dy)
    ) / math.sqrt(vx * vy)


def _quantile(
    values: list[float],
    q: float,
) -> float:
    if not values:
        return math.nan

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (
        (len(ordered) - 1) * q
    )

    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return ordered[lower]

    weight = position - lower

    return (
        ordered[lower]
        * (1.0 - weight)
        + ordered[upper]
        * weight
    )


@dataclass(frozen=True)
class RegimeDiscovery:
    feature: str
    regime_feature: str
    horizon: int
    low_quantile: float
    high_quantile: float
    low_threshold: float
    high_threshold: float
    n_low: int
    n_high: int
    low_correlation: float
    high_correlation: float
    global_correlation: float
    regime_difference: float
    sign_reversal: bool
    dominant_regime: str
    direction_low: int
    direction_high: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        payload = (
            f"{self.feature}|"
            f"{self.regime_feature}|"
            f"{self.horizon}|"
            f"{self.low_quantile:.6f}|"
            f"{self.high_quantile:.6f}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return f"regime:{digest}"


def evaluate_regime(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature: str,
    regime_feature: str,
    horizon: int,
    low_quantile: float = 0.25,
    high_quantile: float = 0.75,
    min_samples_per_regime: int = 30,
) -> RegimeDiscovery | None:
    if not (
        0.0
        < low_quantile
        < high_quantile
        < 1.0
    ):
        raise ValueError(
            "regime quantiles must satisfy "
            "0 < low < high < 1"
        )

    observations = []
    ancestry = set()

    for row in rows:
        x = row.feature(feature)
        state = row.feature(
            regime_feature
        )
        outcome = row.outcome(horizon)

        if not (
            _finite(x)
            and _finite(state)
            and _finite(outcome)
        ):
            continue

        observations.append((x, state, outcome, row.minute))

        ancestry.update(
            row.ancestry(feature)
        )
        ancestry.update(
            row.ancestry(
                regime_feature
            )
        )

    if (
        len(observations)
        < 2 * min_samples_per_regime
    ):
        return None

    states = [
        state
        for _, state, _, _ in observations
    ]

    low_threshold = _quantile(
        states,
        low_quantile,
    )

    high_threshold = _quantile(
        states,
        high_quantile,
    )

    if not (
        _finite(low_threshold)
        and _finite(high_threshold)
        and low_threshold
        < high_threshold
    ):
        return None

    low_minutes = {minute for _, state, _, minute in observations if state <= low_threshold}
    high_minutes = {minute for _, state, _, minute in observations if state >= high_threshold}

    low = [
        (x, outcome)
        for x, state, outcome, _
        in observations
        if state <= low_threshold
    ]

    high = [
        (x, outcome)
        for x, state, outcome, _
        in observations
        if state >= high_threshold
    ]

    if (
        len(low)
        < min_samples_per_regime
        or len(high)
        < min_samples_per_regime
    ):
        return None

    low_corr = _pearson(
        [x for x, _ in low],
        [y for _, y in low],
    )

    high_corr = _pearson(
        [x for x, _ in high],
        [y for _, y in high],
    )

    global_corr = _pearson(
        [
            x
            for x, _, _, _
            in observations
        ],
        [
            outcome
            for _, _, outcome, _
            in observations
        ],
    )

    if not (
        _finite(low_corr)
        and _finite(high_corr)
    ):
        return None

    if not _finite(global_corr):
        global_corr = 0.0

    difference = abs(
        high_corr - low_corr
    )

    sign_reversal = (
        low_corr * high_corr < 0.0
    )

    dominant_regime = (
        "high"
        if abs(high_corr)
        >= abs(low_corr)
        else "low"
    )

    direction_low = (
        1
        if low_corr > 0.0
        else -1
    )

    direction_high = (
        1
        if high_corr > 0.0
        else -1
    )

    # Regime differences are the primary object.
    # A genuine sign reversal receives an explicit,
    # bounded reward.
    reversal_bonus = (
        1.5
        if sign_reversal
        else 1.0
    )

    regime_strength = max(
        abs(low_corr),
        abs(high_corr),
    )

    global_penalty = max(
        0.0,
        regime_strength
        - abs(global_corr),
    )

    score = (
        difference
        * (
            regime_strength
            + global_penalty
        )
        * reversal_bonus
        * math.sqrt(
            min(
                len(low),
                len(high),
            )
        )
    )

    return RegimeDiscovery(
        feature=feature,
        regime_feature=(
            regime_feature
        ),
        horizon=horizon,
        low_quantile=low_quantile,
        high_quantile=high_quantile,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        n_low=len(low),
        n_high=len(high),
        low_correlation=low_corr,
        high_correlation=high_corr,
        global_correlation=(
            global_corr
        ),
        regime_difference=(
            difference
        ),
        sign_reversal=(
            sign_reversal
        ),
        dominant_regime=(
            dominant_regime
        ),
        direction_low=direction_low,
        direction_high=direction_high,
        score=score,
        independent_time_units=min(
            len(low_minutes),
            len(high_minutes),
        ),
        ancestry=tuple(
            sorted(ancestry)
        ),
    )


def discover_regimes(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature_names: Iterable[str],
    regime_feature_names: (
        Iterable[str] | None
    ) = None,
    horizons: tuple[int, ...] = (
        1,
        5,
        10,
        20,
    ),
    quantile_pairs: tuple[
        tuple[float, float],
        ...
    ] = (
        (0.20, 0.80),
        (0.25, 0.75),
        (0.33, 0.67),
    ),
    min_samples_per_regime: int = 30,
    min_regime_difference: float = 0.10,
    max_features: int = 20,
    max_regime_features: int = 12,
    max_results: int = 50,
) -> list[RegimeDiscovery]:
    rows = list(rows)

    features = list(
        dict.fromkeys(feature_names)
    )[:max_features]

    if regime_feature_names is None:
        regime_features = features
    else:
        regime_features = list(
            dict.fromkeys(
                regime_feature_names
            )
        )[:max_regime_features]

    discoveries = []

    for feature in features:
        for regime_feature in (
            regime_features
        ):
            if feature == regime_feature:
                continue

            for (
                low_quantile,
                high_quantile,
            ) in quantile_pairs:
                for horizon in horizons:
                    result = evaluate_regime(
                        rows,
                        feature=feature,
                        regime_feature=(
                            regime_feature
                        ),
                        horizon=horizon,
                        low_quantile=(
                            low_quantile
                        ),
                        high_quantile=(
                            high_quantile
                        ),
                        min_samples_per_regime=(
                            min_samples_per_regime
                        ),
                    )

                    if result is None:
                        continue

                    if (
                        result.regime_difference
                        < min_regime_difference
                    ):
                        continue

                    discoveries.append(
                        result
                    )

    discoveries.sort(
        key=lambda item: (
            item.score,
            item.sign_reversal,
            item.regime_difference,
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
