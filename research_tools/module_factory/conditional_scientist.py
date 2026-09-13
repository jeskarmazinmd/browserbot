"""
Conditional research scientist.

Purpose:
    Discover relationships that are weak or invisible globally
    but become useful inside another observable market state.

Example:
    return_5 may contain little unconditional information,
    but become predictive when volatility_20 is unusually high.

Research only. No live-capital authorization.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from research_tools.module_factory.feature_matrix import FeatureRow


@dataclass(frozen=True)
class ConditionalDiscovery:
    signal_feature: str
    state_feature: str
    horizon: int
    state_direction: str
    state_fraction: float
    observations: int
    conditional_observations: int
    unconditional_correlation: float
    conditional_correlation: float
    unconditional_spread: float
    conditional_spread: float
    improvement: float
    consistency: float
    preferred_sign: int
    score: float
    independent_time_units: int


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

        while (
            j < len(order)
            and values[order[j]]
            == values[order[i]]
        ):
            j += 1

        average = (
            (i + 1) + j
        ) / 2.0

        for k in range(i, j):
            ranks[order[k]] = average

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
        q * (len(ordered) - 1)
    )

    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return ordered[lower]

    fraction = position - lower

    return (
        ordered[lower]
        + fraction
        * (
            ordered[upper]
            - ordered[lower]
        )
    )


def _tail_spread(
    pairs: list[tuple[float, float]],
    *,
    tail_fraction: float,
) -> float:
    if len(pairs) < 4:
        return math.nan

    ordered = sorted(
        pairs,
        key=lambda item: item[0],
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

    low = statistics.fmean(
        y
        for _, y in ordered[:tail_n]
    )

    high = statistics.fmean(
        y
        for _, y in ordered[-tail_n:]
    )

    return high - low


def _day_sign_consistency(
    rows: list[FeatureRow],
    *,
    signal_feature: str,
    state_feature: str,
    horizon: int,
    threshold: float,
    state_direction: str,
    tail_fraction: float,
    preferred_sign: int,
) -> float:
    by_day = {}

    for row in rows:
        day = row.minute.date().isoformat()
        by_day.setdefault(day, []).append(row)

    signs = []

    for day_rows in by_day.values():
        pairs = []

        for row in day_rows:
            signal = row.features.get(
                signal_feature,
                math.nan,
            )

            state = row.features.get(
                state_feature,
                math.nan,
            )

            future = row.forward_returns.get(
                horizon,
                math.nan,
            )

            if not (
                _finite(signal)
                and _finite(state)
                and _finite(future)
            ):
                continue

            selected = (
                state >= threshold
                if state_direction == "high"
                else state <= threshold
            )

            if selected:
                pairs.append(
                    (
                        float(signal),
                        float(future),
                    )
                )

        spread = _tail_spread(
            pairs,
            tail_fraction=tail_fraction,
        )

        if math.isfinite(spread):
            signs.append(
                1
                if spread >= 0
                else -1
            )

    if not signs:
        return 0.0

    return (
        sum(
            sign == preferred_sign
            for sign in signs
        )
        / len(signs)
    )


def analyze_condition(
    rows: list[FeatureRow],
    *,
    signal_feature: str,
    state_feature: str,
    horizon: int,
    state_direction: str,
    state_fraction: float = 0.20,
    tail_fraction: float = 0.20,
    min_conditional_observations: int = 50,
) -> ConditionalDiscovery | None:
    triples = []

    for row in rows:
        signal = row.features.get(
            signal_feature,
            math.nan,
        )

        state = row.features.get(
            state_feature,
            math.nan,
        )

        future = row.forward_returns.get(
            horizon,
            math.nan,
        )

        if (
            _finite(signal)
            and _finite(state)
            and _finite(future)
        ):
            triples.append(
                (
                    float(signal),
                    float(state),
                    float(future),
                    row.minute,
                )
            )

    if len(triples) < min_conditional_observations:
        return None

    states = [
        state
        for _, state, _, _ in triples
    ]

    if state_direction == "high":
        threshold = _quantile(
            states,
            1.0 - state_fraction,
        )

        conditional = [
            (signal, future)
            for signal, state, future, _
            in triples
            if state >= threshold
        ]

    elif state_direction == "low":
        threshold = _quantile(
            states,
            state_fraction,
        )

        conditional = [
            (signal, future)
            for signal, state, future, _
            in triples
            if state <= threshold
        ]

    else:
        raise ValueError(
            "state_direction must be "
            "'low' or 'high'"
        )

    if (
        len(conditional)
        < min_conditional_observations
    ):
        return None

    unconditional_pairs = [
        (signal, future)
        for signal, _, future, _ in triples
    ]

    conditional_minutes = {
        minute
        for _, state, _, minute in triples
        if (
            state >= threshold
            if state_direction == "high"
            else state <= threshold
        )
    }

    unconditional_rho = _spearman(
        [x for x, _ in unconditional_pairs],
        [y for _, y in unconditional_pairs],
    )

    conditional_rho = _spearman(
        [x for x, _ in conditional],
        [y for _, y in conditional],
    )

    unconditional_spread = _tail_spread(
        unconditional_pairs,
        tail_fraction=tail_fraction,
    )

    conditional_spread = _tail_spread(
        conditional,
        tail_fraction=tail_fraction,
    )

    if not (
        math.isfinite(conditional_rho)
        and math.isfinite(
            conditional_spread
        )
    ):
        return None

    unconditional_strength = (
        abs(unconditional_rho)
        if math.isfinite(
            unconditional_rho
        )
        else 0.0
    )

    conditional_strength = abs(
        conditional_rho
    )

    improvement = (
        conditional_strength
        - unconditional_strength
    )

    preferred_sign = (
        1
        if conditional_spread >= 0
        else -1
    )

    consistency = _day_sign_consistency(
        rows,
        signal_feature=signal_feature,
        state_feature=state_feature,
        horizon=horizon,
        threshold=threshold,
        state_direction=state_direction,
        tail_fraction=tail_fraction,
        preferred_sign=preferred_sign,
    )

    # Discovery ranking, not a formal significance test.
    #
    # Reward conditional information and improvement over
    # unconditional behavior. Penalize relationships that
    # only appear in one day.
    score = (
        conditional_strength * 4.0
        + abs(conditional_spread)
        + max(improvement, 0.0) * 3.0
        + consistency
    )

    return ConditionalDiscovery(
        signal_feature=signal_feature,
        state_feature=state_feature,
        horizon=horizon,
        state_direction=state_direction,
        state_fraction=state_fraction,
        observations=len(triples),
        conditional_observations=len(
            conditional
        ),
        unconditional_correlation=(
            unconditional_rho
        ),
        conditional_correlation=(
            conditional_rho
        ),
        unconditional_spread=(
            unconditional_spread
        ),
        conditional_spread=(
            conditional_spread
        ),
        improvement=improvement,
        consistency=consistency,
        preferred_sign=preferred_sign,
        score=score,
        independent_time_units=len(
            conditional_minutes
        ),
    )


def discover(
    rows: list[FeatureRow],
    *,
    signal_features: list[str],
    state_features: list[str],
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    state_fraction: float = 0.20,
    tail_fraction: float = 0.20,
    min_conditional_observations: int = 50,
) -> list[ConditionalDiscovery]:
    results = []

    for signal in signal_features:
        for state in state_features:
            if signal == state:
                continue

            for horizon in horizons:
                for direction in (
                    "low",
                    "high",
                ):
                    result = analyze_condition(
                        rows,
                        signal_feature=signal,
                        state_feature=state,
                        horizon=horizon,
                        state_direction=direction,
                        state_fraction=(
                            state_fraction
                        ),
                        tail_fraction=(
                            tail_fraction
                        ),
                        min_conditional_observations=(
                            min_conditional_observations
                        ),
                    )

                    if result is not None:
                        results.append(result)

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results


def render(
    discoveries: list[ConditionalDiscovery],
    *,
    top: int = 20,
) -> str:
    header = (
        f"{'signal':20} "
        f"{'state':20} "
        f"{'dir':>4} "
        f"{'hor':>3} "
        f"{'n':>6} "
        f"{'cond':>6} "
        f"{'rho0':>7} "
        f"{'rhoC':>7} "
        f"{'gain':>7} "
        f"{'spread':>8} "
        f"{'cons':>5} "
        f"{'score':>7}"
    )

    lines = [
        header,
        "-" * len(header),
    ]

    for result in discoveries[:top]:
        lines.append(
            f"{result.signal_feature:20} "
            f"{result.state_feature:20} "
            f"{result.state_direction:>4} "
            f"{result.horizon:>3} "
            f"{result.observations:>6} "
            f"{result.conditional_observations:>6} "
            f"{result.unconditional_correlation:>7.3f} "
            f"{result.conditional_correlation:>7.3f} "
            f"{result.improvement:>7.3f} "
            f"{result.conditional_spread:>8.3f} "
            f"{result.consistency:>5.2f} "
            f"{result.score:>7.3f}"
        )

    return "\n".join(lines)
