"""
Research Idea Library for Module Factory.

Human knowledge, academic literature, practitioner research,
autonomous discoveries, and evolutionary descendants all enter
the factory through the same representation.

An idea is inspiration, NOT evidence.

No idea may bypass historical testing, unseen validation,
prospective testing, or capital authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


SOURCE_TYPES = (
    "academic",
    "textbook",
    "practitioner",
    "autonomous",
    "residual",
    "evolutionary",
    "wild",
    "human",
)


@dataclass(frozen=True)
class IdeaSource:
    source_type: str
    title: str = ""
    authors: tuple[str, ...] = ()
    year: int | None = None
    locator: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(
                f"unknown source_type: "
                f"{self.source_type}"
            )


@dataclass(frozen=True)
class ResearchIdea:
    concept: str
    mechanism: str
    observables: tuple[str, ...]
    transformations: tuple[str, ...] = ()
    targets: tuple[str, ...] = (
        "future_return",
    )
    conditions: tuple[str, ...] = ()
    scientist_types: tuple[str, ...] = (
        "univariate",
    )
    source: IdeaSource = field(
        default_factory=lambda: IdeaSource(
            source_type="autonomous",
        )
    )
    ancestry: tuple[str, ...] = ()
    novelty: float = 0.5
    confidence_prior: float = 0.5
    assumed_direction: str = "unknown"
    description: str = ""

    def __post_init__(self):
        if not self.concept.strip():
            raise ValueError(
                "concept cannot be empty"
            )

        if not self.mechanism.strip():
            raise ValueError(
                "mechanism cannot be empty"
            )

        if not self.observables:
            raise ValueError(
                "idea requires observables"
            )

        if self.assumed_direction not in (
            "unknown",
            "positive",
            "negative",
        ):
            raise ValueError(
                "invalid assumed_direction"
            )

        if not 0.0 <= self.novelty <= 1.0:
            raise ValueError(
                "novelty must be in [0,1]"
            )

        if not (
            0.0
            <= self.confidence_prior
            <= 1.0
        ):
            raise ValueError(
                "confidence_prior must be "
                "in [0,1]"
            )

    @property
    def idea_id(self) -> str:
        # Source locator deliberately excluded:
        # same conceptual idea from multiple sources should
        # be recognizable as the same research concept.
        payload = {
            "concept": self.concept,
            "mechanism": self.mechanism,
            "observables": sorted(
                self.observables
            ),
            "transformations": sorted(
                self.transformations
            ),
            "targets": sorted(
                self.targets
            ),
            "conditions": sorted(
                self.conditions
            ),
            "scientist_types": sorted(
                self.scientist_types
            ),
        }

        digest = hashlib.sha1(
            json.dumps(
                payload,
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12].upper()

        return f"IDEA-{digest}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["idea_id"] = self.idea_id
        return data


class IdeaLibrary:
    """
    Append-only JSONL idea library.

    Multiple sources may support the same conceptual idea.
    The first canonical idea is retained in current(), while
    all source records remain in the JSONL history.
    """

    def __init__(
        self,
        path: str | Path | None = None,
    ):
        self.path = (
            Path(path)
            if path is not None
            else None
        )

        self._ideas: dict[
            str,
            ResearchIdea,
        ] = {}

        self._sources: dict[
            str,
            list[IdeaSource],
        ] = {}

        if (
            self.path is not None
            and self.path.exists()
        ):
            self._load()

    def _load(self) -> None:
        with self.path.open() as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                payload = json.loads(line)

                source_payload = payload[
                    "source"
                ]

                source = IdeaSource(
                    source_type=source_payload[
                        "source_type"
                    ],
                    title=source_payload.get(
                        "title",
                        "",
                    ),
                    authors=tuple(
                        source_payload.get(
                            "authors",
                            (),
                        )
                    ),
                    year=source_payload.get(
                        "year"
                    ),
                    locator=source_payload.get(
                        "locator",
                        "",
                    ),
                    notes=source_payload.get(
                        "notes",
                        "",
                    ),
                )

                idea = ResearchIdea(
                    concept=payload["concept"],
                    mechanism=payload[
                        "mechanism"
                    ],
                    observables=tuple(
                        payload["observables"]
                    ),
                    transformations=tuple(
                        payload.get(
                            "transformations",
                            (),
                        )
                    ),
                    targets=tuple(
                        payload.get(
                            "targets",
                            (
                                "future_return",
                            ),
                        )
                    ),
                    conditions=tuple(
                        payload.get(
                            "conditions",
                            (),
                        )
                    ),
                    scientist_types=tuple(
                        payload.get(
                            "scientist_types",
                            (
                                "univariate",
                            ),
                        )
                    ),
                    source=source,
                    ancestry=tuple(
                        payload.get(
                            "ancestry",
                            (),
                        )
                    ),
                    novelty=float(
                        payload.get(
                            "novelty",
                            0.5,
                        )
                    ),
                    confidence_prior=float(
                        payload.get(
                            "confidence_prior",
                            0.5,
                        )
                    ),
                    assumed_direction=payload.get(
                        "assumed_direction",
                        "unknown",
                    ),
                    description=payload.get(
                        "description",
                        "",
                    ),
                )

                self._ideas.setdefault(
                    idea.idea_id,
                    idea,
                )

                self._sources.setdefault(
                    idea.idea_id,
                    [],
                ).append(source)

    def add(
        self,
        idea: ResearchIdea,
    ) -> str:
        idea_id = idea.idea_id

        self._ideas.setdefault(
            idea_id,
            idea,
        )

        sources = self._sources.setdefault(
            idea_id,
            [],
        )

        source_key = (
            idea.source.source_type,
            idea.source.title,
            idea.source.locator,
        )

        existing_keys = {
            (
                source.source_type,
                source.title,
                source.locator,
            )
            for source in sources
        }

        if source_key not in existing_keys:
            sources.append(idea.source)

            if self.path is not None:
                self.path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                with self.path.open(
                    "a"
                ) as handle:
                    handle.write(
                        json.dumps(
                            idea.to_dict(),
                            sort_keys=True,
                        )
                        + "\n"
                    )

        return idea_id

    def current(
        self,
    ) -> list[ResearchIdea]:
        return list(
            self._ideas.values()
        )

    def get(
        self,
        idea_id: str,
    ) -> ResearchIdea | None:
        return self._ideas.get(idea_id)

    def sources(
        self,
        idea_id: str,
    ) -> tuple[IdeaSource, ...]:
        return tuple(
            self._sources.get(
                idea_id,
                (),
            )
        )

    def by_source_type(
        self,
        source_type: str,
    ) -> list[ResearchIdea]:
        return [
            idea
            for idea_id, idea
            in self._ideas.items()
            if any(
                source.source_type
                == source_type
                for source
                in self._sources.get(
                    idea_id,
                    (),
                )
            )
        ]

    def __len__(self) -> int:
        return len(self._ideas)


def seed_core_ideas() -> list[ResearchIdea]:
    """
    Small initial conceptual vocabulary.

    These are NOT trading rules. They are broad research
    mechanisms that scientists may interrogate mathematically.
    """

    seeds = [
        (
            "relative_displacement",
            "Assets displaced unusually far relative to peers "
            "may subsequently behave differently.",
            (
                "return",
                "relative_return",
                "cross_sectional_rank",
            ),
            (
                "rank",
                "zscore",
                "difference",
            ),
            (
                "cross_sectional",
                "conditional",
            ),
        ),
        (
            "lead_lag",
            "Information may propagate between market, groups, "
            "and individual securities with measurable delay.",
            (
                "return",
                "relative_return",
                "market_return",
            ),
            (
                "lag",
                "difference",
                "correlation",
            ),
            (
                "time_series",
                "cross_sectional",
                "conditional",
            ),
        ),
        (
            "volatility_state",
            "Predictive relationships may change with the "
            "magnitude or clustering of recent movement.",
            (
                "volatility",
                "return",
                "acceleration",
            ),
            (
                "zscore",
                "rank",
                "ratio",
            ),
            (
                "conditional",
                "distribution",
            ),
        ),
        (
            "serial_dependence",
            "Recent changes may contain persistence, reversal, "
            "or more complex temporal dependence.",
            (
                "return",
                "autocorrelation",
                "acceleration",
                "sign_persistence",
            ),
            (
                "lag",
                "difference",
                "autocorrelation",
            ),
            (
                "time_series",
                "conditional",
            ),
        ),
        (
            "distribution_shift",
            "Changes in the shape of recent return "
            "distributions may precede different future states.",
            (
                "skew",
                "kurtosis",
                "volatility",
                "return",
            ),
            (
                "difference",
                "zscore",
                "rank",
            ),
            (
                "distribution",
                "anomaly",
                "conditional",
            ),
        ),
        (
            "range_state",
            "Location within a recent trading range may interact "
            "with movement, volatility, and persistence.",
            (
                "range_position",
                "return",
                "volatility",
            ),
            (
                "rank",
                "interaction",
                "difference",
            ),
            (
                "conditional",
                "interaction",
            ),
        ),
        (
            "residual_structure",
            "Returns unexplained by common market or existing "
            "signals may contain separate predictive structure.",
            (
                "relative_return",
                "residual_return",
                "return",
            ),
            (
                "residualize",
                "rank",
                "zscore",
            ),
            (
                "residual",
                "cross_sectional",
            ),
        ),
        (
            "rare_state",
            "Unusual multivariate configurations may identify "
            "market states not captured by ordinary thresholds.",
            (
                "return",
                "volatility",
                "range_position",
                "skew",
                "kurtosis",
            ),
            (
                "distance",
                "cluster",
                "anomaly_score",
            ),
            (
                "anomaly",
                "contrarian",
            ),
        ),
    ]

    return [
        ResearchIdea(
            concept=concept,
            mechanism=mechanism,
            observables=observables,
            transformations=transforms,
            targets=(
                "future_return",
                "absolute_future_return",
                "future_cross_sectional_rank",
            ),
            scientist_types=scientists,
            source=IdeaSource(
                source_type="textbook",
                title=(
                    "Module Factory core "
                    "quantitative vocabulary"
                ),
                notes=(
                    "Seed concept only; "
                    "not empirical evidence."
                ),
            ),
            novelty=0.25,
            confidence_prior=0.5,
            assumed_direction="unknown",
        )
        for (
            concept,
            mechanism,
            observables,
            transforms,
            scientists,
        ) in seeds
    ]
