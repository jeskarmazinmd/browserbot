"""
Translate conceptual ResearchIdeas into concrete research
questions for Module Factory specialist scientists.

Translation is deliberately agnostic to trading direction.
"""

from __future__ import annotations

from dataclasses import dataclass

from research_tools.module_factory.idea_library import (
    ResearchIdea,
)
from research_tools.module_factory.research_scientist import (
    DatasetProfile,
    ResearchQuestion,
)


@dataclass(frozen=True)
class TranslatedQuestion:
    idea_id: str
    concept: str
    source_type: str
    question: ResearchQuestion


def _matches(
    observable: str,
    feature: str,
) -> bool:
    normalized = observable.lower()
    feature_lower = feature.lower()

    aliases = {
        "sign_persistence": (
            "up_fraction",
            "sign_persistence",
        ),
        "market_return": (
            "spy_relative",
            "return",
        ),
        "relative_return": (
            "relative_return",
            "spy_relative_return",
        ),
        "cross_sectional_rank": (
            "return",
            "relative_return",
        ),
        "residual_return": (
            "relative_return",
        ),
    }

    candidates = aliases.get(
        normalized,
        (normalized,),
    )

    return any(
        candidate in feature_lower
        for candidate in candidates
    )


def resolve_features(
    idea: ResearchIdea,
    profile: DatasetProfile,
) -> list[str]:
    features = []

    for feature, fp in (
        profile.feature_profiles.items()
    ):
        if (
            fp.finite_fraction < 0.95
            or fp.std <= 1e-12
        ):
            continue

        if any(
            _matches(
                observable,
                feature,
            )
            for observable
            in idea.observables
        ):
            features.append(feature)

    return sorted(set(features))


def translate_idea(
    idea: ResearchIdea,
    profile: DatasetProfile,
    *,
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    max_questions: int = 100,
) -> list[TranslatedQuestion]:
    features = resolve_features(
        idea,
        profile,
    )

    if not features:
        return []

    translated = []

    target_map = {
        "future_return": (
            "predict_future_return"
        ),
        "absolute_future_return": (
            "predict_future_magnitude"
        ),
        "future_cross_sectional_rank": (
            "predict_relative_winner"
        ),
    }

    for scientist in idea.scientist_types:
        for target in idea.targets:
            question_type = target_map.get(
                target,
                "investigate_relationship",
            )

            if scientist == "cross_sectional":
                question_type = (
                    "predict_relative_winner"
                )
                target = (
                    "future_cross_sectional_rank"
                )

            elif scientist == "conditional":
                question_type = (
                    "relationship_by_state"
                )

            elif scientist == "interaction":
                question_type = (
                    "nonlinear_interaction"
                )

            elif scientist == "time_series":
                question_type = (
                    "temporal_dependence"
                )

            elif scientist == "distribution":
                question_type = (
                    "distributional_prediction"
                )

            elif scientist == "residual":
                question_type = (
                    "predict_unexplained_return"
                )
                target = "residual_future_return"

            elif scientist == "anomaly":
                question_type = (
                    "multivariate_unusual_state"
                )

            elif scientist == "contrarian":
                question_type = (
                    "challenge_conventional_structure"
                )

            # Single-feature questions.
            if scientist not in (
                "conditional",
                "interaction",
                "anomaly",
            ):
                for feature in features:
                    for horizon in horizons:
                        translated.append(
                            TranslatedQuestion(
                                idea_id=idea.idea_id,
                                concept=idea.concept,
                                source_type=(
                                    idea.source.source_type
                                ),
                                question=ResearchQuestion(
                                    scientist=scientist,
                                    question_type=(
                                        question_type
                                    ),
                                    target=target,
                                    features=(feature,),
                                    horizon=horizon,
                                    priority=(
                                        0.75
                                        + 0.20
                                        * idea.novelty
                                        + 0.05
                                        * idea.confidence_prior
                                    ),
                                    rationale=(
                                        f"Idea "
                                        f"{idea.idea_id}: "
                                        f"{idea.mechanism}"
                                    ),
                                ),
                            )
                        )

            # Pairwise conditional / interaction questions.
            elif scientist in (
                "conditional",
                "interaction",
            ):
                for i, left in enumerate(
                    features
                ):
                    for right in (
                        features[i + 1:]
                    ):
                        for horizon in horizons:
                            translated.append(
                                TranslatedQuestion(
                                    idea_id=(
                                        idea.idea_id
                                    ),
                                    concept=(
                                        idea.concept
                                    ),
                                    source_type=(
                                        idea.source.source_type
                                    ),
                                    question=ResearchQuestion(
                                        scientist=(
                                            scientist
                                        ),
                                        question_type=(
                                            question_type
                                        ),
                                        target=target,
                                        features=(
                                            left,
                                            right,
                                        ),
                                        horizon=(
                                            horizon
                                        ),
                                        priority=(
                                            0.70
                                            + 0.20
                                            * idea.novelty
                                            + 0.05
                                            * idea.confidence_prior
                                        ),
                                        rationale=(
                                            f"Idea "
                                            f"{idea.idea_id}: "
                                            f"{idea.mechanism}"
                                        ),
                                    ),
                                )
                            )

            # Multivariate anomaly question.
            else:
                translated.append(
                    TranslatedQuestion(
                        idea_id=idea.idea_id,
                        concept=idea.concept,
                        source_type=(
                            idea.source.source_type
                        ),
                        question=ResearchQuestion(
                            scientist=scientist,
                            question_type=(
                                question_type
                            ),
                            target=target,
                            features=tuple(
                                features[:20]
                            ),
                            horizon=max(horizons),
                            priority=(
                                0.65
                                + 0.25
                                * idea.novelty
                            ),
                            rationale=(
                                f"Idea "
                                f"{idea.idea_id}: "
                                f"{idea.mechanism}"
                            ),
                        ),
                    )
                )

    # Deduplicate exact translated questions.
    #
    # ResearchQuestion.key intentionally does not encode the
    # inspiration source. Here we need a stricter translation
    # identity that also preserves the target. This prevents
    # multiple idea targets from collapsing into repeated
    # scientist/feature/horizon work.
    unique = {}

    for item in translated:
        q = item.question

        key = (
            item.idea_id,
            q.scientist,
            q.question_type,
            q.target,
            q.features,
            q.horizon,
        )

        existing = unique.get(key)

        if (
            existing is None
            or q.priority
            > existing.question.priority
        ):
            unique[key] = item

    ordered = sorted(
        unique.values(),
        key=lambda item: (
            -item.question.priority,
            item.question.scientist,
            item.question.features,
            item.question.horizon or 0,
        ),
    )

    return ordered[:max_questions]


def translate_library(
    ideas: list[ResearchIdea],
    profile: DatasetProfile,
    *,
    horizons: tuple[int, ...] = (
        1, 5, 10, 20,
    ),
    max_questions_per_idea: int = 100,
) -> list[TranslatedQuestion]:
    results = []

    for idea in ideas:
        results.extend(
            translate_idea(
                idea,
                profile,
                horizons=horizons,
                max_questions=(
                    max_questions_per_idea
                ),
            )
        )

    return results
