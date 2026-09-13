"""
Agnostic statistical discovery engine for Module Factory.

This module does not know named strategies.

Given generic symbol-minute feature rows, it asks whether any observable
contains repeatable information about future returns.

Discovery statistics include:
- Pearson dependence
- Spearman/rank dependence
- extreme-tail conditional returns
- long-vs-short economic direction
- quantile-bucket response shape
- monotonicity
- standardized effect size
- independent-day consistency
- Benjamini-Hochberg false-discovery control

Research only.  No trading imports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean

from research_tools.module_factory.feature_matrix import FeatureRow


@dataclass
class DayEvidence:
    day: str
    observations: int
    pearson: float
    spearman: float
    low_tail_return: float
    high_tail_return: float
    spread_return: float
    preferred_sign: int
    preferred_edge: float
    effect_size: float
    bucket_means: tuple[float, ...]
    monotonicity: float


@dataclass
class Discovery:
    feature: str
    horizon: int
    days: list[DayEvidence] = field(default_factory=list)
    observations: int = 0
    mean_pearson: float = 0.0
    mean_spearman: float = 0.0
    mean_edge: float = 0.0
    worst_day_edge: float = 0.0
    sign_consistency: float = 0.0
    mean_effect_size: float = 0.0
    mean_monotonicity: float = 0.0
    raw_pvalue: float = 1.0
    bh_pass: bool = False
    score: float = 0.0


def _finite_pair(x, y) -> bool:
    return (
        isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and math.isfinite(x)
        and math.isfinite(y)
    )


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(
        sum((x - m) ** 2 for x in values) / (len(values) - 1)
    )


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return 0.0

    xm = mean(xs)
    ym = mean(ys)

    numerator = sum(
        (x - xm) * (y - ym)
        for x, y in zip(xs, ys)
    )
    xss = sum((x - xm) ** 2 for x in xs)
    yss = sum((y - ym) ** 2 for y in ys)

    denominator = math.sqrt(xss * yss)
    return numerator / denominator if denominator else 0.0


def _ranks(values: list[float]) -> list[float]:
    """
    Average ranks for ties.
    """
    ordered = sorted(
        enumerate(values),
        key=lambda item: item[1],
    )

    result = [0.0] * len(values)
    i = 0

    while i < len(ordered):
        j = i + 1

        while (
            j < len(ordered)
            and ordered[j][1] == ordered[i][1]
        ):
            j += 1

        average_rank = (i + 1 + j) / 2.0

        for k in range(i, j):
            result[ordered[k][0]] = average_rank

        i = j

    return result


def _spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    return _pearson(_ranks(xs), _ranks(ys))


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return ordered[lower]

    fraction = position - lower
    return (
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )


def _bucket_means(
    xs: list[float],
    ys: list[float],
    buckets: int,
) -> tuple[float, ...]:
    if not xs or buckets < 2:
        return tuple()

    pairs = sorted(zip(xs, ys), key=lambda p: p[0])
    result: list[float] = []

    n = len(pairs)

    for bucket in range(buckets):
        start = bucket * n // buckets
        end = (bucket + 1) * n // buckets

        values = [y for _, y in pairs[start:end]]
        result.append(mean(values) if values else 0.0)

    return tuple(result)


def _monotonicity(bucket_means: tuple[float, ...]) -> float:
    if len(bucket_means) < 3:
        return 0.0

    positions = list(range(len(bucket_means)))
    return _spearman(
        [float(x) for x in positions],
        list(bucket_means),
    )


def _normal_two_sided_pvalue(z: float) -> float:
    """
    Normal approximation. Adequate for cheap discovery screening.
    More expensive validation can use stronger methods later.
    """
    return math.erfc(abs(z) / math.sqrt(2.0))


def _correlation_pvalue(r: float, n: int) -> float:
    if n < 4 or abs(r) >= 1.0:
        return 0.0 if abs(r) >= 1.0 and n >= 4 else 1.0

    denominator = max(1e-15, 1.0 - r * r)
    t = abs(r) * math.sqrt((n - 2) / denominator)

    # Normal approximation deliberately used only as a screening statistic.
    return _normal_two_sided_pvalue(t)


def _day_evidence(
    day: str,
    pairs: list[tuple[float, float]],
    *,
    tail_fraction: float,
    buckets: int,
) -> DayEvidence | None:

    if len(pairs) < max(20, buckets * 2):
        return None

    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]

    low_cut = _quantile(xs, tail_fraction)
    high_cut = _quantile(xs, 1.0 - tail_fraction)

    low_returns = [
        y for x, y in pairs
        if x <= low_cut
    ]
    high_returns = [
        y for x, y in pairs
        if x >= high_cut
    ]

    if not low_returns or not high_returns:
        return None

    low_mean = mean(low_returns)
    high_mean = mean(high_returns)

    # Positive means high feature values outperform low feature values.
    spread = high_mean - low_mean

    # Economic sign is inferred rather than specified.
    preferred_sign = 1 if spread >= 0 else -1
    preferred_edge = abs(spread)

    pooled = _std(low_returns + high_returns)
    effect = abs(spread) / pooled if pooled else 0.0

    bucket_values = _bucket_means(xs, ys, buckets)

    return DayEvidence(
        day=day,
        observations=len(pairs),
        pearson=_pearson(xs, ys),
        spearman=_spearman(xs, ys),
        low_tail_return=low_mean,
        high_tail_return=high_mean,
        spread_return=spread,
        preferred_sign=preferred_sign,
        preferred_edge=preferred_edge,
        effect_size=effect,
        bucket_means=bucket_values,
        monotonicity=_monotonicity(bucket_values),
    )


def _bh_passes(
    discoveries: list[Discovery],
    q: float,
) -> set[tuple[str, int]]:
    """
    Benjamini-Hochberg FDR control across the discovery population.
    """
    ordered = sorted(
        discoveries,
        key=lambda x: x.raw_pvalue,
    )

    threshold_index = -1

    for i, item in enumerate(ordered, start=1):
        threshold = q * i / len(ordered)

        if item.raw_pvalue <= threshold:
            threshold_index = i - 1

    if threshold_index < 0:
        return set()

    cutoff = ordered[threshold_index].raw_pvalue

    return {
        (item.feature, item.horizon)
        for item in discoveries
        if item.raw_pvalue <= cutoff
    }


def discover(
    rows_by_day: dict[str, list[FeatureRow]],
    *,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
    tail_fraction: float = 0.10,
    buckets: int = 10,
    min_observations_per_day: int = 100,
    fdr_q: float = 0.05,
) -> list[Discovery]:

    feature_names = sorted({
        feature
        for rows in rows_by_day.values()
        for row in rows
        for feature in row.features
    })

    discoveries: list[Discovery] = []

    for feature in feature_names:
        for horizon in horizons:
            days: list[DayEvidence] = []
            combined_x: list[float] = []
            combined_y: list[float] = []

            for day, rows in sorted(rows_by_day.items()):
                pairs = []

                for row in rows:
                    x = row.features.get(feature)
                    y = row.forward_returns.get(horizon)

                    if _finite_pair(x, y):
                        pairs.append((float(x), float(y)))

                if len(pairs) < min_observations_per_day:
                    continue

                evidence = _day_evidence(
                    day,
                    pairs,
                    tail_fraction=tail_fraction,
                    buckets=buckets,
                )

                if evidence is None:
                    continue

                days.append(evidence)
                combined_x.extend(x for x, _ in pairs)
                combined_y.extend(y for _, y in pairs)

            if not days:
                continue

            combined_spearman = _spearman(
                combined_x,
                combined_y,
            )

            dominant_sign = (
                1
                if sum(day.spread_return for day in days) >= 0
                else -1
            )

            signed_edges = [
                dominant_sign * day.spread_return
                for day in days
            ]

            consistency = (
                sum(edge > 0 for edge in signed_edges)
                / len(signed_edges)
            )

            average_edge = mean(signed_edges)
            worst_edge = min(signed_edges)

            average_effect = mean(
                day.effect_size for day in days
            )

            average_monotonicity = mean(
                dominant_sign * day.monotonicity
                for day in days
            )

            pvalue = _correlation_pvalue(
                combined_spearman,
                len(combined_x),
            )

            # Score deliberately rewards independent-day robustness,
            # not merely huge sample size or a tiny p-value.
            score = (
                0.35 * average_edge
                + 0.35 * worst_edge
                + 0.15 * average_effect
                + 0.10 * consistency
                + 0.05 * max(0.0, average_monotonicity)
            )

            discoveries.append(
                Discovery(
                    feature=feature,
                    horizon=horizon,
                    days=days,
                    observations=len(combined_x),
                    mean_pearson=mean(
                        day.pearson for day in days
                    ),
                    mean_spearman=mean(
                        day.spearman for day in days
                    ),
                    mean_edge=average_edge,
                    worst_day_edge=worst_edge,
                    sign_consistency=consistency,
                    mean_effect_size=average_effect,
                    mean_monotonicity=average_monotonicity,
                    raw_pvalue=pvalue,
                    score=score,
                )
            )

    passes = _bh_passes(discoveries, fdr_q)

    for item in discoveries:
        item.bh_pass = (
            item.feature,
            item.horizon,
        ) in passes

    return sorted(
        discoveries,
        key=lambda x: (
            x.bh_pass,
            x.sign_consistency,
            x.worst_day_edge,
            x.score,
        ),
        reverse=True,
    )


def render(discoveries: list[Discovery], top: int = 30) -> str:
    lines = []

    lines.append(
        "feature                         hor days      n "
        "rho      edge    worst   consist effect   mono     BH"
    )
    lines.append("-" * 112)

    for item in discoveries[:top]:
        lines.append(
            f"{item.feature:<31} "
            f"{item.horizon:>3} "
            f"{len(item.days):>4} "
            f"{item.observations:>7} "
            f"{item.mean_spearman:>7.4f} "
            f"{item.mean_edge:>8.4f} "
            f"{item.worst_day_edge:>8.4f} "
            f"{item.sign_consistency:>7.2f} "
            f"{item.mean_effect_size:>7.3f} "
            f"{item.mean_monotonicity:>7.3f} "
            f"{'PASS' if item.bh_pass else '-':>6}"
        )

    return "\n".join(lines)
