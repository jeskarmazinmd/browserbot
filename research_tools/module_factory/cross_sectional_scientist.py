"""
Cross-sectional research scientist.

Question:
    At the same market minute, does a feature distinguish stocks
    that subsequently outperform from stocks that subsequently
    underperform?

The scientist works within timestamp cross-sections rather than
pooling all symbol-minutes together. This removes much of the
common market/time component and focuses on relative selection.

Research only. No trading or live-capital authorization.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

from research_tools.module_factory.feature_matrix import FeatureRow


@dataclass(frozen=True)
class CrossSectionMinuteEvidence:
    minute: object
    observations: int
    rank_correlation: float
    low_feature_return: float
    high_feature_return: float
    high_minus_low: float


@dataclass(frozen=True)
class CrossSectionDiscovery:
    feature: str
    horizon: int
    minutes: int
    observations: int
    mean_rank_correlation: float
    median_rank_correlation: float
    positive_rank_fraction: float
    mean_high_minus_low: float
    median_high_minus_low: float
    positive_spread_fraction: float
    spread_t_stat: float
    preferred_sign: int
    score: float


def _finite(value) -> bool:
    return (
        isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(
        range(len(values)),
        key=values.__getitem__,
    )

    ranks = [0.0] * len(values)

    i = 0

    while i < len(order):
        j = i + 1
        value = values[order[i]]

        while (
            j < len(order)
            and values[order[j]] == value
        ):
            j += 1

        average_rank = (
            (i + 1) + j
        ) / 2.0

        for k in range(i, j):
            ranks[order[k]] = average_rank

        i = j

    return ranks


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
        return math.nan

    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)

    numerator = sum(
        (x - mx) * (y - my)
        for x, y in zip(xs, ys)
    )

    dx = sum(
        (x - mx) ** 2
        for x in xs
    )

    dy = sum(
        (y - my) ** 2
        for y in ys
    )

    denominator = math.sqrt(dx * dy)

    if denominator <= 1e-18:
        return math.nan

    return numerator / denominator


def _spearman(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
        return math.nan

    return _pearson(
        _average_ranks(xs),
        _average_ranks(ys),
    )


def analyze_minute(
    rows: list[FeatureRow],
    *,
    feature: str,
    horizon: int,
    tail_fraction: float = 0.20,
    min_cross_section: int = 20,
) -> CrossSectionMinuteEvidence | None:
    pairs = []

    for row in rows:
        x = row.features.get(
            feature,
            math.nan,
        )

        y = row.forward_returns.get(
            horizon,
            math.nan,
        )

        if _finite(x) and _finite(y):
            pairs.append(
                (float(x), float(y))
            )

    if len(pairs) < min_cross_section:
        return None

    xs = [
        pair[0]
        for pair in pairs
    ]

    ys = [
        pair[1]
        for pair in pairs
    ]

    rho = _spearman(xs, ys)

    ordered = sorted(
        pairs,
        key=lambda pair: pair[0],
    )

    tail_n = max(
        1,
        int(
            math.floor(
                len(ordered)
                * tail_fraction
            )
        ),
    )

    low_return = statistics.fmean(
        y
        for _, y in ordered[:tail_n]
    )

    high_return = statistics.fmean(
        y
        for _, y in ordered[-tail_n:]
    )

    return CrossSectionMinuteEvidence(
        minute=rows[0].minute,
        observations=len(pairs),
        rank_correlation=rho,
        low_feature_return=low_return,
        high_feature_return=high_return,
        high_minus_low=(
            high_return - low_return
        ),
    )


def discover_feature(
    rows: list[FeatureRow],
    *,
    feature: str,
    horizon: int,
    tail_fraction: float = 0.20,
    min_cross_section: int = 20,
    min_minutes: int = 10,
) -> CrossSectionDiscovery | None:
    by_minute = defaultdict(list)

    for row in rows:
        by_minute[row.minute].append(row)

    evidence = []

    for minute_rows in by_minute.values():
        item = analyze_minute(
            minute_rows,
            feature=feature,
            horizon=horizon,
            tail_fraction=tail_fraction,
            min_cross_section=min_cross_section,
        )

        if item is not None:
            evidence.append(item)

    if len(evidence) < min_minutes:
        return None

    correlations = [
        item.rank_correlation
        for item in evidence
        if math.isfinite(
            item.rank_correlation
        )
    ]

    spreads = [
        item.high_minus_low
        for item in evidence
        if math.isfinite(
            item.high_minus_low
        )
    ]

    if not correlations or not spreads:
        return None

    mean_rho = statistics.fmean(
        correlations
    )

    median_rho = statistics.median(
        correlations
    )

    positive_rho_fraction = (
        sum(
            rho > 0
            for rho in correlations
        )
        / len(correlations)
    )

    mean_spread = statistics.fmean(
        spreads
    )

    median_spread = statistics.median(
        spreads
    )

    positive_spread_fraction = (
        sum(
            spread > 0
            for spread in spreads
        )
        / len(spreads)
    )

    if len(spreads) > 1:
        spread_std = statistics.stdev(
            spreads
        )
    else:
        spread_std = 0.0

    if spread_std <= 1e-18:
        spread_t = (
            math.inf
            if abs(mean_spread) > 1e-18
            else 0.0
        )
    else:
        spread_t = (
            mean_spread
            / (
                spread_std
                / math.sqrt(
                    len(spreads)
                )
            )
        )

    preferred_sign = (
        1
        if mean_spread >= 0
        else -1
    )

    directional_consistency = max(
        positive_spread_fraction,
        1.0 - positive_spread_fraction,
    )

    rank_consistency = max(
        positive_rho_fraction,
        1.0 - positive_rho_fraction,
    )

    # Ranking score, not a formal p-value.
    # Rewards:
    # - absolute cross-sectional rank information
    # - economically visible tail spread
    # - minute-to-minute directional consistency
    # - agreement between rank and tail evidence
    score = (
        abs(mean_rho) * 4.0
        + abs(mean_spread)
        + directional_consistency
        + 0.5 * rank_consistency
    )

    return CrossSectionDiscovery(
        feature=feature,
        horizon=horizon,
        minutes=len(evidence),
        observations=sum(
            item.observations
            for item in evidence
        ),
        mean_rank_correlation=mean_rho,
        median_rank_correlation=median_rho,
        positive_rank_fraction=(
            positive_rho_fraction
        ),
        mean_high_minus_low=mean_spread,
        median_high_minus_low=median_spread,
        positive_spread_fraction=(
            positive_spread_fraction
        ),
        spread_t_stat=spread_t,
        preferred_sign=preferred_sign,
        score=score,
    )


def discover(
    rows: list[FeatureRow],
    *,
    features: list[str] | None = None,
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    tail_fraction: float = 0.20,
    min_cross_section: int = 20,
    min_minutes: int = 10,
) -> list[CrossSectionDiscovery]:
    if not rows:
        return []

    if features is None:
        features = sorted({
            feature
            for row in rows
            for feature in row.features
        })

    results = []

    for feature in features:
        for horizon in horizons:
            result = discover_feature(
                rows,
                feature=feature,
                horizon=horizon,
                tail_fraction=tail_fraction,
                min_cross_section=(
                    min_cross_section
                ),
                min_minutes=min_minutes,
            )

            if result is not None:
                results.append(result)

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results


def render(
    discoveries: list[CrossSectionDiscovery],
    *,
    top: int = 20,
) -> str:
    header = (
        f"{'feature':30} "
        f"{'hor':>3} "
        f"{'mins':>5} "
        f"{'n':>8} "
        f"{'rho':>8} "
        f"{'spread':>9} "
        f"{'consist':>8} "
        f"{'t':>8} "
        f"{'sign':>5} "
        f"{'score':>8}"
    )

    lines = [
        header,
        "-" * len(header),
    ]

    for result in discoveries[:top]:
        lines.append(
            f"{result.feature:30} "
            f"{result.horizon:>3} "
            f"{result.minutes:>5} "
            f"{result.observations:>8} "
            f"{result.mean_rank_correlation:>8.4f} "
            f"{result.mean_high_minus_low:>9.4f} "
            f"{max(result.positive_spread_fraction, 1.0 - result.positive_spread_fraction):>8.3f} "
            f"{result.spread_t_stat:>8.2f} "
            f"{result.preferred_sign:>5} "
            f"{result.score:>8.4f}"
        )

    return "\n".join(lines)
