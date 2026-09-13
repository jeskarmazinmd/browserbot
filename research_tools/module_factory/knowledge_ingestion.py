"""
Knowledge ingestion for Module Factory.

External material is converted into conceptual ResearchIdeas.

Critical scientific boundary:

    SOURCE MATERIAL -> INSPIRATION -> HYPOTHESIS

never:

    SOURCE MATERIAL -> TRADING TRUTH

The ingestion layer stores provenance and conceptual mechanisms.
It does not claim that a paper, textbook, blog, trader, or human
idea is empirically valid in our market data.

No internet access occurs in this module. Retrieval is a separate
research-side concern so that ingestion remains deterministic and
reproducible.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from research_tools.module_factory.idea_library import (
    IdeaLibrary,
    IdeaSource,
    ResearchIdea,
    SOURCE_TYPES,
)


STANCE_VALUES = (
    "proposes",
    "supports",
    "challenges",
    "surveys",
    "neutral",
)


@dataclass(frozen=True)
class KnowledgeDocument:
    source_type: str
    title: str
    text: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    locator: str = ""
    stance: str = "neutral"
    tags: tuple[str, ...] = ()
    metadata: dict = field(
        default_factory=dict
    )

    def __post_init__(self):
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(
                f"unknown source_type: "
                f"{self.source_type}"
            )

        if not self.title.strip():
            raise ValueError(
                "document title cannot be empty"
            )

        if not self.text.strip():
            raise ValueError(
                "document text cannot be empty"
            )

        if self.stance not in STANCE_VALUES:
            raise ValueError(
                f"invalid stance: {self.stance}"
            )

    @property
    def document_id(self) -> str:
        payload = {
            "source_type": self.source_type,
            "title": self.title.strip(),
            "authors": list(self.authors),
            "year": self.year,
            "locator": self.locator,
        }

        digest = hashlib.sha1(
            json.dumps(
                payload,
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12].upper()

        return f"DOC-{digest}"


@dataclass(frozen=True)
class IdeaProposal:
    """
    Structured interpretation of source material.

    This is the boundary where an external extractor, an LLM,
    a human, or another deterministic process can say:

        "This document suggests investigating mechanism X
         using observables A/B/C."

    The proposal itself is still not evidence.
    """

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
    novelty: float = 0.5
    confidence_prior: float = 0.5
    assumed_direction: str = "unknown"
    description: str = ""


@dataclass(frozen=True)
class IngestionRecord:
    document_id: str
    idea_id: str
    source_type: str
    stance: str
    concept: str


# Concept vocabulary used only for deterministic suggestion.
#
# This is deliberately broad. It helps bootstrap ingestion when
# source material contains familiar quantitative concepts.
# It is NOT intended to be exhaustive and does not replace richer
# external extraction later.
CONCEPT_LEXICON = {
    "momentum": {
        "terms": (
            "momentum",
            "trend following",
            "trend-following",
            "continuation",
        ),
        "observables": (
            "return",
            "relative_return",
        ),
        "transforms": (
            "rank",
            "zscore",
            "lag",
        ),
        "scientists": (
            "time_series",
            "cross_sectional",
            "conditional",
        ),
    },
    "reversal": {
        "terms": (
            "reversal",
            "mean reversion",
            "mean-reversion",
            "contrarian",
        ),
        "observables": (
            "return",
            "relative_return",
            "range_position",
        ),
        "transforms": (
            "rank",
            "zscore",
            "difference",
        ),
        "scientists": (
            "time_series",
            "cross_sectional",
            "conditional",
        ),
    },
    "lead_lag": {
        "terms": (
            "lead-lag",
            "lead lag",
            "information diffusion",
            "delayed response",
        ),
        "observables": (
            "return",
            "relative_return",
            "market_return",
        ),
        "transforms": (
            "lag",
            "difference",
            "correlation",
        ),
        "scientists": (
            "time_series",
            "cross_sectional",
            "conditional",
        ),
    },
    "volatility": {
        "terms": (
            "volatility",
            "variance",
            "volatility clustering",
        ),
        "observables": (
            "volatility",
            "return",
            "acceleration",
        ),
        "transforms": (
            "zscore",
            "rank",
            "ratio",
        ),
        "scientists": (
            "distribution",
            "conditional",
            "anomaly",
        ),
    },
    "liquidity_microstructure": {
        "terms": (
            "liquidity",
            "bid-ask",
            "bid ask",
            "spread",
            "market microstructure",
            "order flow",
        ),
        "observables": (
            "return",
            "volatility",
            "spread",
            "volume",
        ),
        "transforms": (
            "difference",
            "ratio",
            "zscore",
            "rank",
        ),
        "scientists": (
            "conditional",
            "interaction",
            "time_series",
        ),
    },
    "cross_sectional_dispersion": {
        "terms": (
            "cross-sectional dispersion",
            "cross sectional dispersion",
            "dispersion",
        ),
        "observables": (
            "return",
            "relative_return",
            "volatility",
        ),
        "transforms": (
            "rank",
            "zscore",
            "difference",
        ),
        "scientists": (
            "cross_sectional",
            "conditional",
            "distribution",
        ),
    },
    "statistical_arbitrage": {
        "terms": (
            "statistical arbitrage",
            "pairs trading",
            "pairs-trading",
            "cointegration",
        ),
        "observables": (
            "return",
            "relative_return",
            "residual_return",
        ),
        "transforms": (
            "residualize",
            "difference",
            "ratio",
            "zscore",
        ),
        "scientists": (
            "residual",
            "cross_sectional",
            "time_series",
        ),
    },
    "regime_change": {
        "terms": (
            "regime",
            "change point",
            "change-point",
            "structural break",
            "state switching",
        ),
        "observables": (
            "return",
            "volatility",
            "autocorrelation",
            "skew",
            "kurtosis",
        ),
        "transforms": (
            "difference",
            "zscore",
            "cluster",
        ),
        "scientists": (
            "conditional",
            "anomaly",
            "distribution",
        ),
    },
    "nonlinear_interaction": {
        "terms": (
            "nonlinear",
            "non-linear",
            "interaction",
            "machine learning",
            "deep learning",
        ),
        "observables": (
            "return",
            "relative_return",
            "volatility",
            "range_position",
        ),
        "transforms": (
            "interaction",
            "ratio",
            "rank",
            "zscore",
        ),
        "scientists": (
            "interaction",
            "conditional",
            "evolutionary",
        ),
    },
    "anomaly_detection": {
        "terms": (
            "anomaly detection",
            "outlier",
            "unusual state",
            "rare state",
            "clustering",
        ),
        "observables": (
            "return",
            "volatility",
            "range_position",
            "skew",
            "kurtosis",
        ),
        "transforms": (
            "distance",
            "cluster",
            "anomaly_score",
        ),
        "scientists": (
            "anomaly",
            "contrarian",
        ),
    },
    "serial_dependence": {
        "terms": (
            "autocorrelation",
            "serial correlation",
            "serial dependence",
            "variance ratio",
        ),
        "observables": (
            "return",
            "autocorrelation",
            "sign_persistence",
        ),
        "transforms": (
            "lag",
            "autocorrelation",
            "difference",
        ),
        "scientists": (
            "time_series",
            "conditional",
        ),
    },
    "distribution_shape": {
        "terms": (
            "skewness",
            "kurtosis",
            "tail risk",
            "extreme value",
            "distribution shift",
            "entropy",
        ),
        "observables": (
            "skew",
            "kurtosis",
            "volatility",
            "return",
        ),
        "transforms": (
            "difference",
            "zscore",
            "rank",
        ),
        "scientists": (
            "distribution",
            "anomaly",
            "conditional",
        ),
    },
}


def normalize_text(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text.strip().lower(),
    )


def suggest_proposals(
    document: KnowledgeDocument,
) -> list[IdeaProposal]:
    """
    Conservative deterministic bootstrap extractor.

    Later, an external literature researcher can provide richer
    structured IdeaProposals. This function simply guarantees
    that ingestion itself does not require an LLM or internet.
    """

    haystack = normalize_text(
        " ".join(
            (
                document.title,
                document.text,
                " ".join(document.tags),
            )
        )
    )

    proposals = []

    for concept, spec in (
        CONCEPT_LEXICON.items()
    ):
        matched = [
            term
            for term in spec["terms"]
            if term in haystack
        ]

        if not matched:
            continue

        proposals.append(
            IdeaProposal(
                concept=concept,
                mechanism=(
                    "External source discusses "
                    f"{concept.replace('_', ' ')}. "
                    "Investigate whether related "
                    "observable structure contains "
                    "predictive or state information "
                    "in our own market data."
                ),
                observables=tuple(
                    spec["observables"]
                ),
                transformations=tuple(
                    spec["transforms"]
                ),
                targets=(
                    "future_return",
                    "absolute_future_return",
                    "future_cross_sectional_rank",
                ),
                scientist_types=tuple(
                    spec["scientists"]
                ),
                novelty=0.35,
                confidence_prior=0.5,
                assumed_direction="unknown",
                description=(
                    "Matched source terms: "
                    + ", ".join(matched)
                ),
            )
        )

    return proposals


def proposal_to_idea(
    document: KnowledgeDocument,
    proposal: IdeaProposal,
) -> ResearchIdea:
    source_notes = (
        f"stance={document.stance}; "
        f"document_id={document.document_id}"
    )

    if proposal.description:
        source_notes += (
            f"; {proposal.description}"
        )

    return ResearchIdea(
        concept=proposal.concept,
        mechanism=proposal.mechanism,
        observables=proposal.observables,
        transformations=(
            proposal.transformations
        ),
        targets=proposal.targets,
        conditions=proposal.conditions,
        scientist_types=(
            proposal.scientist_types
        ),
        source=IdeaSource(
            source_type=document.source_type,
            title=document.title,
            authors=document.authors,
            year=document.year,
            locator=document.locator,
            notes=source_notes,
        ),
        ancestry=(
            document.document_id,
        ),
        novelty=proposal.novelty,
        confidence_prior=(
            proposal.confidence_prior
        ),
        assumed_direction=(
            proposal.assumed_direction
        ),
        description=(
            proposal.description
        ),
    )


def ingest_document(
    library: IdeaLibrary,
    document: KnowledgeDocument,
    *,
    proposals: Iterable[
        IdeaProposal
    ] | None = None,
) -> list[IngestionRecord]:
    """
    Ingest one document.

    Explicit proposals are preferred when supplied. Otherwise
    deterministic lexical suggestions bootstrap candidate ideas.
    """

    proposal_list = list(
        proposals
        if proposals is not None
        else suggest_proposals(document)
    )

    records = []

    for proposal in proposal_list:
        idea = proposal_to_idea(
            document,
            proposal,
        )

        idea_id = library.add(idea)

        records.append(
            IngestionRecord(
                document_id=(
                    document.document_id
                ),
                idea_id=idea_id,
                source_type=(
                    document.source_type
                ),
                stance=document.stance,
                concept=proposal.concept,
            )
        )

    return records


def ingest_documents(
    library: IdeaLibrary,
    documents: Iterable[
        KnowledgeDocument
    ],
) -> list[IngestionRecord]:
    records = []

    for document in documents:
        records.extend(
            ingest_document(
                library,
                document,
            )
        )

    return records


def load_documents_jsonl(
    path: str | Path,
) -> list[KnowledgeDocument]:
    documents = []

    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            payload = json.loads(line)

            documents.append(
                KnowledgeDocument(
                    source_type=payload[
                        "source_type"
                    ],
                    title=payload["title"],
                    text=payload["text"],
                    authors=tuple(
                        payload.get(
                            "authors",
                            (),
                        )
                    ),
                    year=payload.get("year"),
                    locator=payload.get(
                        "locator",
                        "",
                    ),
                    stance=payload.get(
                        "stance",
                        "neutral",
                    ),
                    tags=tuple(
                        payload.get(
                            "tags",
                            (),
                        )
                    ),
                    metadata=payload.get(
                        "metadata",
                        {},
                    ),
                )
            )

    return documents
