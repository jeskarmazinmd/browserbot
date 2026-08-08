"""Core research-lab data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TemporalClass(str, Enum):
    ENTRY_KNOWN = "ENTRY_KNOWN"
    PAST_DERIVED = "PAST_DERIVED"
    POST_ENTRY = "POST_ENTRY"
    UNKNOWN = "UNKNOWN"


class CoverageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    PROSPECTIVE_ONLY = "PROSPECTIVE_ONLY"
    MISSING = "MISSING"


@dataclass(frozen=True)
class FieldProvenance:
    field: str
    temporal_class: TemporalClass
    reason: str
    confidence: str = "heuristic"


@dataclass
class StrategySpec:
    strategy_id: str
    path: Path
    family: str = ""
    paper_only: bool | None = None
    config: dict[str, Any] = field(default_factory=dict)
    constants: dict[str, Any] = field(default_factory=dict)
    structural_tags: set[str] = field(default_factory=set)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class DataSourceSpec:
    path: Path
    format: str
    size_bytes: int
    roles: set[str] = field(default_factory=set)
    fields: set[str] = field(default_factory=set)
    records_sampled: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchCapability:
    name: str
    state: CoverageState
    reason: str
    evidence: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchDimension:
    name: str
    category: str
    description: str
    required_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchCoverage:
    dimension: SearchDimension
    readiness: str
    attempts: int
    strategies_touched: int
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlindSpot:
    category: str
    description: str
    severity: str = "INFO"
    source: str | None = None


@dataclass
class DiscoveryReport:
    strategies: list[StrategySpec] = field(default_factory=list)
    sources: list[DataSourceSpec] = field(default_factory=list)
    provenance: list[FieldProvenance] = field(default_factory=list)
    capabilities: list[ResearchCapability] = field(default_factory=list)
    blind_spots: list[BlindSpot] = field(default_factory=list)
