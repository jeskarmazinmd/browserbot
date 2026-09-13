"""
Persistent external research corpus for Module Factory.

The corpus stores SOURCE MATERIAL and provenance.
The IdeaLibrary stores CONCEPTUAL INSPIRATION.
ExperimentMemory stores EMPIRICAL TEST HISTORY.

Those layers must remain separate.

A source entering this corpus does not become evidence that a
trading relationship exists. It merely becomes available to the
research-scientist layer for hypothesis generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from research_tools.module_factory.knowledge_ingestion import (
    KnowledgeDocument,
)


@dataclass(frozen=True)
class CorpusRecord:
    document_id: str
    source_type: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    locator: str
    text: str
    stance: str
    tags: tuple[str, ...]
    retrieved_at: str
    retrieval_method: str
    content_hash: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_document(
        cls,
        document: KnowledgeDocument,
        *,
        retrieved_at: str | None = None,
        retrieval_method: str = "manual",
    ) -> "CorpusRecord":
        normalized = " ".join(
            document.text.split()
        )

        content_hash = hashlib.sha256(
            normalized.encode()
        ).hexdigest()

        return cls(
            document_id=document.document_id,
            source_type=document.source_type,
            title=document.title,
            authors=document.authors,
            year=document.year,
            locator=document.locator,
            text=document.text,
            stance=document.stance,
            tags=document.tags,
            retrieved_at=(
                retrieved_at
                or datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            retrieval_method=retrieval_method,
            content_hash=content_hash,
            metadata=dict(document.metadata),
        )

    def to_document(self) -> KnowledgeDocument:
        return KnowledgeDocument(
            source_type=self.source_type,
            title=self.title,
            text=self.text,
            authors=self.authors,
            year=self.year,
            locator=self.locator,
            stance=self.stance,
            tags=self.tags,
            metadata=dict(self.metadata),
        )


class KnowledgeCorpus:
    """
    Append-only JSONL corpus.

    Current state is indexed by document_id.
    Exact duplicate source records are not re-appended.
    """

    def __init__(
        self,
        path: str | Path,
    ):
        self.path = Path(path)
        self._records: dict[
            str,
            CorpusRecord,
        ] = {}

        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with self.path.open() as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                payload = json.loads(line)

                record = CorpusRecord(
                    document_id=payload[
                        "document_id"
                    ],
                    source_type=payload[
                        "source_type"
                    ],
                    title=payload["title"],
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
                    text=payload["text"],
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
                    retrieved_at=payload[
                        "retrieved_at"
                    ],
                    retrieval_method=payload.get(
                        "retrieval_method",
                        "unknown",
                    ),
                    content_hash=payload[
                        "content_hash"
                    ],
                    metadata=payload.get(
                        "metadata",
                        {},
                    ),
                )

                self._records[
                    record.document_id
                ] = record

    def add(
        self,
        document: KnowledgeDocument,
        *,
        retrieval_method: str = "manual",
        retrieved_at: str | None = None,
    ) -> bool:
        record = CorpusRecord.from_document(
            document,
            retrieved_at=retrieved_at,
            retrieval_method=retrieval_method,
        )

        existing = self._records.get(
            record.document_id
        )

        if (
            existing is not None
            and existing.content_hash
            == record.content_hash
        ):
            return False

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.path.open("a") as handle:
            handle.write(
                json.dumps(
                    asdict(record),
                    sort_keys=True,
                )
                + "\n"
            )

        self._records[
            record.document_id
        ] = record

        return True

    def add_many(
        self,
        documents: Iterable[
            KnowledgeDocument
        ],
        *,
        retrieval_method: str = "manual",
    ) -> int:
        added = 0

        for document in documents:
            added += int(
                self.add(
                    document,
                    retrieval_method=(
                        retrieval_method
                    ),
                )
            )

        return added

    def get(
        self,
        document_id: str,
    ) -> CorpusRecord | None:
        return self._records.get(
            document_id
        )

    def current(
        self,
    ) -> list[CorpusRecord]:
        return list(
            self._records.values()
        )

    def documents(
        self,
    ) -> list[KnowledgeDocument]:
        return [
            record.to_document()
            for record in self.current()
        ]

    def by_source_type(
        self,
        source_type: str,
    ) -> list[CorpusRecord]:
        return [
            record
            for record
            in self.current()
            if record.source_type
            == source_type
        ]

    def by_tag(
        self,
        tag: str,
    ) -> list[CorpusRecord]:
        needle = tag.lower()

        return [
            record
            for record
            in self.current()
            if any(
                item.lower() == needle
                for item in record.tags
            )
        ]

    def unseen_for_library(
        self,
        known_document_ids: set[str],
    ) -> list[KnowledgeDocument]:
        return [
            record.to_document()
            for record
            in self.current()
            if record.document_id
            not in known_document_ids
        ]

    def __len__(self) -> int:
        return len(self._records)


def seed_research_documents(
) -> list[KnowledgeDocument]:
    """
    Initial REAL literature seed set.

    Text is a compact research-oriented paraphrase of each source,
    not copied paper text. The source locator preserves provenance.

    These records provide ideas only.
    """

    return [
        KnowledgeDocument(
            source_type="academic",
            title=(
                "How and When are High-Frequency "
                "Stock Returns Predictable?"
            ),
            authors=(
                "Yacine Ait-Sahalia",
                "Jianqing Fan",
                "Lirong Xue",
                "Yifeng Zhou",
            ),
            year=2022,
            locator=(
                "https://www.nber.org/papers/w30366"
            ),
            text=(
                "Studies ultra-high-frequency stock return and "
                "event-duration predictability using machine "
                "learning. Relevant predictor families arise "
                "from trades, quotes, price, volume and "
                "transaction events, with predictability "
                "varying across stocks and market states. "
                "Inspires microstructure, event-state, "
                "liquidity, volatility, interaction and "
                "conditional research rather than assuming "
                "a trading direction."
            ),
            stance="supports",
            tags=(
                "high_frequency",
                "microstructure",
                "machine_learning",
                "liquidity",
                "volatility",
                "conditional",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title=(
                "Intraday Market Predictability: "
                "A Machine Learning Approach"
            ),
            year=2021,
            locator=(
                "https://academic.oup.com/jfec/"
                "article-abstract/21/2/485/6400345"
            ),
            text=(
                "Studies five-minute equity-market returns "
                "using lagged cross-sectional constituent "
                "returns with regularized linear and nonlinear "
                "models. Constituent returns contain predictive "
                "information beyond aggregate market returns, "
                "trend and liquidity characteristics. "
                "Predictability varies with time of day, "
                "volatility and illiquidity. Inspires "
                "cross-sectional lead-lag, nonlinear "
                "interaction, regime and conditional research."
            ),
            stance="supports",
            tags=(
                "intraday",
                "cross_sectional",
                "lead_lag",
                "machine_learning",
                "regime",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title="Predicting Relative Returns",
            authors=(
                "Valentin Haddad",
                "Serhiy Kozak",
                "Shrihari Santosh",
            ),
            year=2017,
            locator=(
                "https://www.nber.org/papers/w23886"
            ),
            text=(
                "Argues that relative-return dimensions can "
                "be substantially more predictable than "
                "aggregate returns. Cross-sectional and latent "
                "portfolio dimensions may reveal information "
                "hidden when forecasting each asset or market "
                "level independently. Inspires residualization, "
                "relative-return prediction, principal "
                "components and cross-sectional research."
            ),
            stance="supports",
            tags=(
                "relative_return",
                "cross_sectional",
                "residual",
                "latent_factor",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title="Mosaics of Predictability",
            authors=(
                "Lin William Cong",
                "Guanhao Feng",
                "Jingyu He",
                "Yuanzhi Wang",
            ),
            year=2026,
            locator=(
                "https://www.nber.org/papers/w35158"
            ),
            text=(
                "Models return predictability as heterogeneous, "
                "asset-specific and state-dependent rather than "
                "universal. Interpretable partitioning locates "
                "persistent subsets where forecasting signals "
                "are stronger and others where noise dominates. "
                "Inspires regime discovery, conditional "
                "relationships, clustering, anomaly detection "
                "and explicit searches for where a signal works "
                "rather than merely whether it works globally."
            ),
            stance="supports",
            tags=(
                "state_dependence",
                "regime",
                "clustering",
                "conditional",
                "heterogeneity",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title=(
                "Market Microstructure and "
                "Stock Return Predictions"
            ),
            authors=(
                "Roger D. Huang",
                "Hans R. Stoll",
            ),
            year=1994,
            locator=(
                "https://academic.oup.com/rfs/"
                "article-abstract/7/1/179/1568543"
            ),
            text=(
                "Investigates short-run stock-return "
                "predictability from microstructure variables "
                "and lagged index-futures returns at five-minute "
                "frequency. Transaction-price location relative "
                "to quote midpoint and lagged market information "
                "motivate tests of quote state, spread state, "
                "lead-lag and short-horizon reversal or "
                "continuation without assuming the sign in "
                "advance."
            ),
            stance="supports",
            tags=(
                "microstructure",
                "lead_lag",
                "intraday",
                "spread",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title=(
                "Selection of a Portfolio of Pairs "
                "Based on Cointegration"
            ),
            authors=(
                "Joao Caldeira",
                "Guilherme V. Moura",
            ),
            year=2013,
            locator=(
                "https://papers.ssrn.com/sol3/"
                "papers.cfm?abstract_id=2196391"
            ),
            text=(
                "Uses cointegration to identify relationships "
                "among stocks and models resulting residual "
                "spreads for statistical-arbitrage research. "
                "Inspires residual, equilibrium, multivariate "
                "relative-value and mean-reversion hypotheses, "
                "while requiring our own transaction-cost and "
                "out-of-sample validation."
            ),
            stance="supports",
            tags=(
                "statistical_arbitrage",
                "cointegration",
                "residual",
                "mean_reversion",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title=(
                "The Virtue of Complexity "
                "in Return Prediction"
            ),
            authors=(
                "Bryan T. Kelly",
                "Semyon Malamud",
                "Kangying Zhou",
            ),
            year=2022,
            locator=(
                "https://www.nber.org/papers/w30217"
            ),
            text=(
                "Studies complex high-dimensional return "
                "prediction and provides motivation for "
                "allowing nonlinear and richly parameterized "
                "models rather than restricting research to "
                "small simple forecasting specifications. "
                "Inspires interaction and evolutionary "
                "research, while complexity remains subject "
                "to independent validation and economic costs."
            ),
            stance="supports",
            tags=(
                "complexity",
                "machine_learning",
                "nonlinear",
                "interaction",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title="AI-Powered Finance Scholarship",
            authors=(
                "Robert Novy-Marx",
                "Mihail Z. Velikov",
            ),
            year=2025,
            locator=(
                "https://www.nber.org/papers/w33363"
            ),
            text=(
                "Demonstrates large-scale automated generation "
                "and screening of stock-return predictor ideas, "
                "including mining tens of thousands of candidate "
                "signals before applying a standardized anomaly "
                "assessment protocol. Inspires broad automated "
                "hypothesis generation but, more importantly, "
                "strong multiple-testing controls, standardized "
                "falsification and comparison against existing "
                "discoveries."
            ),
            stance="surveys",
            tags=(
                "automation",
                "multiple_testing",
                "anomalies",
                "falsification",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title=(
                "Characteristics Are Covariances: "
                "A Unified Model of Risk and Return"
            ),
            authors=(
                "Bryan Kelly",
                "Seth Pruitt",
                "Yinan Su",
            ),
            year=2018,
            locator=(
                "https://www.nber.org/papers/w24540"
            ),
            text=(
                "Uses instrumented principal components to "
                "combine observable characteristics with latent "
                "factors and time-varying loadings. Inspires "
                "latent-factor extraction, residualization, "
                "dynamic exposures and tests separating common "
                "factor structure from idiosyncratic predictive "
                "structure."
            ),
            stance="supports",
            tags=(
                "latent_factor",
                "pca",
                "residual",
                "cross_sectional",
            ),
        ),
        KnowledgeDocument(
            source_type="academic",
            title="Stock Return Predictability: Is it There?",
            authors=(
                "Andrew Ang",
                "Geert Bekaert",
            ),
            year=2001,
            locator=(
                "https://www.nber.org/papers/w8207"
            ),
            text=(
                "Shows why apparent return predictability can "
                "fail finite-sample corrections, longer samples "
                "or broader geographic tests. Included primarily "
                "as a falsification lesson: relationships should "
                "be challenged for sample dependence, horizon "
                "dependence and instability rather than accepted "
                "because an initial regression looks strong."
            ),
            stance="challenges",
            tags=(
                "falsification",
                "robustness",
                "finite_sample",
                "predictability",
            ),
        ),
    ]
