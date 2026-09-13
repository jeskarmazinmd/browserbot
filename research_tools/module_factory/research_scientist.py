"""
Autonomous data-scientist layer for Module Factory.

This layer sits above raw mathematical search.

Its job is to:
1. characterize the dataset,
2. identify potentially interesting structures,
3. formulate explicit research questions,
4. dispatch those questions to specialist research modes,
5. preserve the distinction between:
       statistical observation
       -> hypothesis
       -> validation
       -> trading-module engineering

It does NOT authorize live trading.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from research_tools.module_factory.feature_matrix import FeatureRow


SCIENTIST_TYPES = (
    "univariate",
    "cross_sectional",
    "conditional",
    "interaction",
    "time_series",
    "distribution",
    "residual",
    "anomaly",
    "contrarian",
    "evolutionary",
)


@dataclass(frozen=True)
class FeatureProfile:
    feature: str
    observations: int
    finite_fraction: float
    mean: float
    std: float
    minimum: float
    p01: float
    p05: float
    median: float
    p95: float
    p99: float
    maximum: float
    zero_fraction: float
    unique_approx: int
    extreme_ratio: float


@dataclass(frozen=True)
class DatasetProfile:
    days: int
    rows: int
    symbols: int
    features: int
    start_minute: str | None
    end_minute: str | None
    rows_by_day: dict[str, int]
    rows_by_symbol: dict[str, int]
    feature_profiles: dict[str, FeatureProfile]
    highly_correlated_pairs: tuple[
        tuple[str, str, float], ...
    ] = ()


@dataclass(frozen=True)
class ResearchQuestion:
    scientist: str
    question_type: str
    target: str
    features: tuple[str, ...] = ()
    horizon: int | None = None
    priority: float = 0.0
    rationale: str = ""

    @property
    def key(self) -> tuple:
        return (
            self.scientist,
            self.question_type,
            self.target,
            self.features,
            self.horizon,
        )


@dataclass
class ResearchAgenda:
    profile: DatasetProfile
    questions: list[ResearchQuestion] = field(
        default_factory=list
    )

    def by_scientist(
        self,
    ) -> dict[str, list[ResearchQuestion]]:
        result = defaultdict(list)

        for question in self.questions:
            result[question.scientist].append(
                question
            )

        return dict(result)


def _finite(values: Iterable[float]) -> list[float]:
    return [
        float(value)
        for value in values
        if isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]


def _quantile(
    sorted_values: list[float],
    q: float,
) -> float:
    if not sorted_values:
        return math.nan

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return sorted_values[lower]

    fraction = position - lower

    return (
        sorted_values[lower]
        + fraction
        * (
            sorted_values[upper]
            - sorted_values[lower]
        )
    )


def _profile_feature(
    feature: str,
    values: list[float],
) -> FeatureProfile:
    total = len(values)
    finite = _finite(values)

    if not finite:
        return FeatureProfile(
            feature=feature,
            observations=total,
            finite_fraction=0.0,
            mean=math.nan,
            std=math.nan,
            minimum=math.nan,
            p01=math.nan,
            p05=math.nan,
            median=math.nan,
            p95=math.nan,
            p99=math.nan,
            maximum=math.nan,
            zero_fraction=0.0,
            unique_approx=0,
            extreme_ratio=math.inf,
        )

    ordered = sorted(finite)

    mean = statistics.fmean(finite)
    std = (
        statistics.pstdev(finite)
        if len(finite) > 1
        else 0.0
    )

    median = _quantile(ordered, 0.50)
    p99 = _quantile(ordered, 0.99)

    abs_ordered = sorted(abs(x) for x in finite)
    abs_median = _quantile(abs_ordered, 0.50)
    abs_p99 = _quantile(abs_ordered, 0.99)

    if abs_median <= 1e-12:
        extreme_ratio = (
            math.inf
            if abs_p99 > 1e-12
            else 1.0
        )
    else:
        extreme_ratio = (
            abs_p99 / abs_median
        )

    # Approximate cardinality without retaining giant sets.
    if len(finite) <= 10000:
        sample = finite
    else:
        step = max(1, len(finite) // 10000)
        sample = finite[::step][:10000]

    unique_approx = len({
        round(value, 12)
        for value in sample
    })

    return FeatureProfile(
        feature=feature,
        observations=total,
        finite_fraction=(
            len(finite) / total
            if total
            else 0.0
        ),
        mean=mean,
        std=std,
        minimum=ordered[0],
        p01=_quantile(ordered, 0.01),
        p05=_quantile(ordered, 0.05),
        median=median,
        p95=_quantile(ordered, 0.95),
        p99=p99,
        maximum=ordered[-1],
        zero_fraction=(
            sum(abs(x) <= 1e-12 for x in finite)
            / len(finite)
        ),
        unique_approx=unique_approx,
        extreme_ratio=extreme_ratio,
    )


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    pairs = [
        (float(x), float(y))
        for x, y in zip(xs, ys)
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and math.isfinite(float(x))
        and math.isfinite(float(y))
    ]

    if len(pairs) < 3:
        return math.nan

    x = [item[0] for item in pairs]
    y = [item[1] for item in pairs]

    mx = statistics.fmean(x)
    my = statistics.fmean(y)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in zip(x, y)
    )

    dx = sum((a - mx) ** 2 for a in x)
    dy = sum((b - my) ** 2 for b in y)

    denominator = math.sqrt(dx * dy)

    if denominator <= 1e-18:
        return math.nan

    return numerator / denominator


def profile_dataset(
    rows_by_day: dict[str, list[FeatureRow]],
    *,
    correlation_sample: int = 5000,
    correlation_threshold: float = 0.95,
) -> DatasetProfile:
    rows = [
        row
        for day_rows in rows_by_day.values()
        for row in day_rows
    ]

    symbols = Counter(
        row.symbol
        for row in rows
    )

    feature_names = sorted({
        feature
        for row in rows
        for feature in row.features
    })

    feature_values = {
        feature: [
            row.features.get(feature, math.nan)
            for row in rows
        ]
        for feature in feature_names
    }

    profiles = {
        feature: _profile_feature(
            feature,
            values,
        )
        for feature, values
        in feature_values.items()
    }

    minutes = sorted(
        row.minute
        for row in rows
    )

    # Deterministic evenly-spaced correlation sample.
    if len(rows) <= correlation_sample:
        sample_rows = rows
    else:
        step = max(
            1,
            len(rows) // correlation_sample,
        )
        sample_rows = rows[
            ::step
        ][:correlation_sample]

    correlated = []

    for i, left in enumerate(feature_names):
        left_values = [
            row.features.get(left, math.nan)
            for row in sample_rows
        ]

        for right in feature_names[i + 1:]:
            right_values = [
                row.features.get(
                    right,
                    math.nan,
                )
                for row in sample_rows
            ]

            rho = _pearson(
                left_values,
                right_values,
            )

            if (
                math.isfinite(rho)
                and abs(rho)
                >= correlation_threshold
            ):
                correlated.append(
                    (
                        left,
                        right,
                        rho,
                    )
                )

    correlated.sort(
        key=lambda item: abs(item[2]),
        reverse=True,
    )

    return DatasetProfile(
        days=len(rows_by_day),
        rows=len(rows),
        symbols=len(symbols),
        features=len(feature_names),
        start_minute=(
            minutes[0].isoformat()
            if minutes
            else None
        ),
        end_minute=(
            minutes[-1].isoformat()
            if minutes
            else None
        ),
        rows_by_day={
            day: len(day_rows)
            for day, day_rows
            in sorted(rows_by_day.items())
        },
        rows_by_symbol=dict(symbols),
        feature_profiles=profiles,
        highly_correlated_pairs=tuple(
            correlated
        ),
    )


def formulate_questions(
    profile: DatasetProfile,
    *,
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    max_questions: int = 500,
) -> list[ResearchQuestion]:
    questions: list[ResearchQuestion] = []

    usable = [
        feature
        for feature, fp
        in profile.feature_profiles.items()
        if fp.finite_fraction >= 0.95
        and fp.std > 1e-12
        and fp.unique_approx >= 10
    ]

    unstable = {
        feature
        for feature, fp
        in profile.feature_profiles.items()
        if (
            not math.isfinite(
                fp.extreme_ratio
            )
            or fp.extreme_ratio > 1000
        )
    }

    # 1. Simple predictive structure.
    for feature in usable:
        for horizon in horizons:
            questions.append(
                ResearchQuestion(
                    scientist="univariate",
                    question_type=(
                        "predict_future_return"
                    ),
                    target="future_return",
                    features=(feature,),
                    horizon=horizon,
                    priority=1.0,
                    rationale=(
                        "Test whether this observable "
                        "contains directional or nonlinear "
                        "information about future return."
                    ),
                )
            )

    # 2. Cross-sectional structure.
    if profile.symbols >= 20:
        for feature in usable:
            for horizon in horizons:
                questions.append(
                    ResearchQuestion(
                        scientist="cross_sectional",
                        question_type=(
                            "predict_relative_winner"
                        ),
                        target=(
                            "future_cross_sectional_rank"
                        ),
                        features=(feature,),
                        horizon=horizon,
                        priority=1.15,
                        rationale=(
                            "Ask whether this feature "
                            "distinguishes subsequent winners "
                            "from losers at the same time."
                        ),
                    )
                )

    # 3. Distribution / large-move prediction.
    for feature in usable:
        for horizon in horizons:
            questions.append(
                ResearchQuestion(
                    scientist="distribution",
                    question_type=(
                        "predict_future_magnitude"
                    ),
                    target="absolute_future_return",
                    features=(feature,),
                    horizon=horizon,
                    priority=0.90,
                    rationale=(
                        "A variable may predict movement "
                        "magnitude even when it does not "
                        "predict direction."
                    ),
                )
            )

    # 4. Time-series behavior for naturally temporal features.
    temporal_tokens = (
        "return",
        "acceleration",
        "autocorr",
        "volatility",
        "up_fraction",
    )

    for feature in usable:
        if any(
            token in feature
            for token in temporal_tokens
        ):
            for horizon in horizons:
                questions.append(
                    ResearchQuestion(
                        scientist="time_series",
                        question_type=(
                            "persistence_or_reversal"
                        ),
                        target="future_return",
                        features=(feature,),
                        horizon=horizon,
                        priority=1.05,
                        rationale=(
                            "Determine whether the state "
                            "persists, reverses, or changes "
                            "behavior across horizons."
                        ),
                    )
                )

    # 5. Conditional research:
    # use broad state variables rather than every possible pair.
    state_features = [
        feature
        for feature in usable
        if any(
            token in feature
            for token in (
                "volatility",
                "range_position",
                "autocorr",
                "kurtosis",
                "skew",
            )
        )
    ]

    predictive_features = [
        feature
        for feature in usable
        if any(
            token in feature
            for token in (
                "return",
                "acceleration",
                "up_fraction",
            )
        )
    ]

    for signal in predictive_features:
        for state in state_features:
            if signal == state:
                continue

            questions.append(
                ResearchQuestion(
                    scientist="conditional",
                    question_type=(
                        "relationship_by_state"
                    ),
                    target="future_return",
                    features=(
                        signal,
                        state,
                    ),
                    horizon=20,
                    priority=0.85,
                    rationale=(
                        "Test whether a weak or unstable "
                        "relationship becomes useful only "
                        "inside a particular market state."
                    ),
                )
            )

    # 6. Interaction scientist gets a bounded,
    # non-pathological cross-family set.
    family = {
        feature: feature.rsplit("_", 1)[0]
        for feature in usable
    }

    interaction_count = 0

    for i, left in enumerate(usable):
        if left in unstable:
            continue

        for right in usable[i + 1:]:
            if right in unstable:
                continue

            if family[left] == family[right]:
                continue

            questions.append(
                ResearchQuestion(
                    scientist="interaction",
                    question_type=(
                        "nonlinear_interaction"
                    ),
                    target="future_return",
                    features=(left, right),
                    horizon=20,
                    priority=0.75,
                    rationale=(
                        "Investigate whether two different "
                        "feature families jointly contain "
                        "information absent individually."
                    ),
                )
            )

            interaction_count += 1

            if interaction_count >= 100:
                break

        if interaction_count >= 100:
            break

    # 7. Anomaly scientist.
    if len(usable) >= 3:
        questions.append(
            ResearchQuestion(
                scientist="anomaly",
                question_type=(
                    "multivariate_unusual_state"
                ),
                target="future_return_distribution",
                features=tuple(usable[:20]),
                horizon=20,
                priority=0.70,
                rationale=(
                    "Look for unusual multivariate states "
                    "without assuming their economic meaning "
                    "in advance."
                ),
            )
        )

    # 8. Contrarian scientist deliberately investigates
    # numerically awkward variables rather than silently
    # discarding them.
    for feature in sorted(unstable):
        questions.append(
            ResearchQuestion(
                scientist="contrarian",
                question_type=(
                    "pathological_feature_structure"
                ),
                target="future_return",
                features=(feature,),
                horizon=20,
                priority=0.40,
                rationale=(
                    "This feature has extreme numerical "
                    "behavior. Determine whether that is "
                    "pure pathology or a meaningful rare "
                    "market-state indicator."
                ),
            )
        )

    # Deduplicate.
    unique = {}

    for question in questions:
        existing = unique.get(question.key)

        if (
            existing is None
            or question.priority
            > existing.priority
        ):
            unique[question.key] = question

    ordered = sorted(
        unique.values(),
        key=lambda q: (
            -q.priority,
            q.scientist,
            q.question_type,
            q.features,
            q.horizon or 0,
        ),
    )

    return ordered[:max_questions]


def build_agenda(
    rows_by_day: dict[str, list[FeatureRow]],
    *,
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    max_questions: int = 500,
) -> ResearchAgenda:
    profile = profile_dataset(
        rows_by_day
    )

    questions = formulate_questions(
        profile,
        horizons=horizons,
        max_questions=max_questions,
    )

    return ResearchAgenda(
        profile=profile,
        questions=questions,
    )


def render_agenda(
    agenda: ResearchAgenda,
) -> str:
    profile = agenda.profile
    by_scientist = agenda.by_scientist()

    lines = [
        "MODULE FACTORY — DATA SCIENTIST",
        "=" * 72,
        (
            f"days={profile.days} "
            f"rows={profile.rows} "
            f"symbols={profile.symbols} "
            f"features={profile.features}"
        ),
        "",
        "RESEARCH AGENDA",
    ]

    for scientist in SCIENTIST_TYPES:
        count = len(
            by_scientist.get(
                scientist,
                [],
            )
        )

        lines.append(
            f"  {scientist:<18} {count:>4} questions"
        )

    lines.extend(
        [
            "",
            "DATA DIAGNOSTICS",
            (
                "  highly correlated pairs: "
                f"{len(profile.highly_correlated_pairs)}"
            ),
        ]
    )

    unstable = [
        fp
        for fp in profile.feature_profiles.values()
        if (
            not math.isfinite(fp.extreme_ratio)
            or fp.extreme_ratio > 1000
        )
    ]

    lines.append(
        f"  numerically extreme features: "
        f"{len(unstable)}"
    )

    lines.extend(
        [
            "",
            "TOP RESEARCH QUESTIONS",
        ]
    )

    for question in agenda.questions[:20]:
        lines.append(
            "  "
            f"[{question.scientist}] "
            f"{question.question_type} "
            f"{','.join(question.features)} "
            f"h={question.horizon} "
            f"priority={question.priority:.2f}"
        )

    return "\n".join(lines)
