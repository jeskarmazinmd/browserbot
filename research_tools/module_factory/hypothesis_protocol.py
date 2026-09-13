"""
Scientific hypothesis protocol for Module Factory.

Purpose
-------
Convert discoveries from many scientist types into one immutable,
auditable hypothesis representation.

Core scientific rule:

    Discovery may design a hypothesis.
    Freezing ends design.
    Validation may judge the frozen hypothesis, but may not alter it.

Changing a feature, parameter, threshold, lag, direction, horizon,
control, regime definition, or other specification creates a NEW
hypothesis identity.

No market data is loaded by this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class HypothesisState(str, Enum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"
    VALIDATED_PASS = "VALIDATED_PASS"
    VALIDATED_FAIL = "VALIDATED_FAIL"


class DatasetRole(str, Enum):
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"


def _canonicalize(
    value: Any,
) -> Any:
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(
                value[key]
            )
            for key in sorted(
                value,
                key=lambda item: str(item),
            )
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _canonicalize(item)
            for item in value
        ]

    if isinstance(value, set):
        return sorted(
            (
                _canonicalize(item)
                for item in value
            ),
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ) or value is None:
        return value

    raise TypeError(
        "unsupported hypothesis value: "
        f"{type(value).__name__}"
    )


def _canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class DataDeclaration:
    dataset_id: str
    role: DatasetRole
    sealed: bool = False

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError(
                "dataset_id cannot be empty"
            )


@dataclass(frozen=True)
class HypothesisSpecification:
    scientist: str
    discovery_id: str
    target: str
    horizon: int
    features: tuple[str, ...]
    parameters: tuple[
        tuple[str, Any],
        ...
    ]
    direction: int | None
    ancestry: tuple[str, ...]
    provenance: tuple[str, ...]
    discovery_dataset_ids: tuple[
        str,
        ...
    ]
    multiple_testing_family: str
    tests_considered: int
    min_samples: int
    min_events: int

    def __post_init__(self) -> None:
        if not self.scientist.strip():
            raise ValueError(
                "scientist cannot be empty"
            )

        if not self.discovery_id.strip():
            raise ValueError(
                "discovery_id cannot be empty"
            )

        if not self.target.strip():
            raise ValueError(
                "target cannot be empty"
            )

        if self.horizon <= 0:
            raise ValueError(
                "horizon must be positive"
            )

        if not self.features:
            raise ValueError(
                "at least one feature is required"
            )

        if len(set(self.features)) != len(
            self.features
        ):
            raise ValueError(
                "features must be unique"
            )

        if self.direction not in (
            None,
            -1,
            1,
        ):
            raise ValueError(
                "direction must be -1, +1, "
                "or None"
            )

        if self.tests_considered < 1:
            raise ValueError(
                "tests_considered must be >= 1"
            )

        if self.min_samples < 1:
            raise ValueError(
                "min_samples must be >= 1"
            )

        if self.min_events < 0:
            raise ValueError(
                "min_events must be >= 0"
            )

        names = [
            name
            for name, _ in self.parameters
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "parameter names must be unique"
            )

        if tuple(sorted(names)) != tuple(
            names
        ):
            raise ValueError(
                "parameters must be sorted "
                "by name"
            )

        # Force validation of serializability and NaN/inf rejection.
        _canonical_json(
            self.identity_payload()
        )

    def identity_payload(
        self,
    ) -> dict[str, Any]:
        return {
            "scientist":
                self.scientist,
            "discovery_id":
                self.discovery_id,
            "target":
                self.target,
            "horizon":
                self.horizon,
            "features":
                self.features,
            "parameters":
                self.parameters,
            "direction":
                self.direction,
            "ancestry":
                tuple(
                    sorted(
                        set(
                            self.ancestry
                        )
                    )
                ),
            "provenance":
                tuple(
                    sorted(
                        set(
                            self.provenance
                        )
                    )
                ),
            "discovery_dataset_ids":
                tuple(
                    sorted(
                        set(
                            self.discovery_dataset_ids
                        )
                    )
                ),
            "multiple_testing_family":
                self.multiple_testing_family,
            "tests_considered":
                self.tests_considered,
            "min_samples":
                self.min_samples,
            "min_events":
                self.min_events,
        }

    @property
    def hypothesis_id(self) -> str:
        digest = hashlib.sha256(
            _canonical_json(
                self.identity_payload()
            ).encode()
        ).hexdigest()[:20]

        return f"hypothesis:{digest}"


@dataclass(frozen=True)
class FrozenHypothesis:
    specification: HypothesisSpecification
    specification_hash: str
    state: HypothesisState = (
        HypothesisState.FROZEN
    )

    @property
    def hypothesis_id(self) -> str:
        return (
            self.specification.hypothesis_id
        )


@dataclass(frozen=True)
class ValidationEvidence:
    hypothesis_id: str
    dataset_id: str
    specification_hash: str
    n_samples: int
    n_events: int
    primary_effect: float
    adjusted_p_value: float | None
    symbol_concentration: float
    time_concentration: float
    parameter_stability: float
    estimated_cost_bps: float
    effective_sample_size: float | None = None
    net_effect: float | None = None
    lag1_dependence: float | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.n_samples < 0:
            raise ValueError(
                "n_samples must be >= 0"
            )

        if self.n_events < 0:
            raise ValueError(
                "n_events must be >= 0"
            )

        for name, value in (
            (
                "symbol_concentration",
                self.symbol_concentration,
            ),
            (
                "time_concentration",
                self.time_concentration,
            ),
            (
                "parameter_stability",
                self.parameter_stability,
            ),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name} must be in [0, 1]"
                )

        if self.estimated_cost_bps < 0.0:
            raise ValueError(
                "estimated_cost_bps "
                "must be >= 0"
            )

        if (
            self.effective_sample_size
            is not None
            and (
                self.effective_sample_size
                < 0.0
                or self.effective_sample_size
                > self.n_samples
            )
        ):
            raise ValueError(
                "effective_sample_size must "
                "be in [0, n_samples]"
            )

        if (
            self.net_effect is not None
            and not (
                float("-inf")
                < self.net_effect
                < float("inf")
            )
        ):
            raise ValueError(
                "net_effect must be finite"
            )

        if (
            self.lag1_dependence
            is not None
            and not (
                -1.0
                <= self.lag1_dependence
                <= 1.0
            )
        ):
            raise ValueError(
                "lag1_dependence must be "
                "in [-1, 1]"
            )

        if (
            self.adjusted_p_value
            is not None
            and not (
                0.0
                <= self.adjusted_p_value
                <= 1.0
            )
        ):
            raise ValueError(
                "adjusted_p_value must be "
                "None or in [0, 1]"
            )


@dataclass(frozen=True)
class ValidationDecision:
    hypothesis_id: str
    dataset_id: str
    state: HypothesisState
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.state
            == HypothesisState.VALIDATED_PASS
        )


@dataclass(frozen=True)
class ValidationPolicy:
    min_abs_effect: float = 0.05
    max_adjusted_p_value: (
        float | None
    ) = 0.05
    max_symbol_concentration: float = 0.35
    max_time_concentration: float = 0.35
    min_parameter_stability: float = 0.60
    min_effective_sample_size: float = 30.0
    require_positive_net_effect: bool = True

    def __post_init__(self) -> None:
        if self.min_abs_effect < 0.0:
            raise ValueError(
                "min_abs_effect must be >= 0"
            )

        for name, value in (
            (
                "max_symbol_concentration",
                self.max_symbol_concentration,
            ),
            (
                "max_time_concentration",
                self.max_time_concentration,
            ),
            (
                "min_parameter_stability",
                self.min_parameter_stability,
            ),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name} must be in [0, 1]"
                )

        if self.min_effective_sample_size < 0.0:
            raise ValueError(
                "min_effective_sample_size "
                "must be >= 0"
            )

        if (
            self.max_adjusted_p_value
            is not None
            and not (
                0.0
                <= self.max_adjusted_p_value
                <= 1.0
            )
        ):
            raise ValueError(
                "max_adjusted_p_value must "
                "be None or in [0, 1]"
            )


def make_specification(
    *,
    scientist: str,
    discovery_id: str,
    target: str,
    horizon: int,
    features: Iterable[str],
    parameters: Mapping[
        str,
        Any,
    ] | None = None,
    direction: int | None,
    ancestry: Iterable[str] = (),
    provenance: Iterable[str] = (),
    discovery_dataset_ids: Iterable[
        str
    ] = (),
    multiple_testing_family: str,
    tests_considered: int,
    min_samples: int,
    min_events: int = 0,
) -> HypothesisSpecification:
    return HypothesisSpecification(
        scientist=scientist,
        discovery_id=discovery_id,
        target=target,
        horizon=horizon,
        features=tuple(features),
        parameters=tuple(
            sorted(
                (
                    str(name),
                    _canonicalize(value),
                )
                for name, value
                in (
                    parameters
                    or {}
                ).items()
            )
        ),
        direction=direction,
        ancestry=tuple(ancestry),
        provenance=tuple(provenance),
        discovery_dataset_ids=tuple(
            discovery_dataset_ids
        ),
        multiple_testing_family=(
            multiple_testing_family
        ),
        tests_considered=(
            tests_considered
        ),
        min_samples=min_samples,
        min_events=min_events,
    )


def specification_hash(
    specification: HypothesisSpecification,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            specification.identity_payload()
        ).encode()
    ).hexdigest()


def freeze_hypothesis(
    specification: HypothesisSpecification,
) -> FrozenHypothesis:
    return FrozenHypothesis(
        specification=specification,
        specification_hash=(
            specification_hash(
                specification
            )
        ),
    )


def assert_validation_access(
    frozen: FrozenHypothesis,
    dataset: DataDeclaration,
) -> None:
    if frozen.state != (
        HypothesisState.FROZEN
    ):
        raise PermissionError(
            "validation requires a "
            "FROZEN hypothesis"
        )

    if dataset.role != (
        DatasetRole.VALIDATION
    ):
        raise PermissionError(
            "dataset is not declared "
            "for validation"
        )

    if dataset.dataset_id in (
        frozen.specification
        .discovery_dataset_ids
    ):
        raise PermissionError(
            "discovery data cannot be "
            "reused as unseen validation"
        )

    if dataset.sealed:
        raise PermissionError(
            "validation dataset remains sealed"
        )


def unseal_for_validation(
    frozen: FrozenHypothesis,
    dataset: DataDeclaration,
) -> DataDeclaration:
    """
    Explicit firewall transition.

    A validation dataset may be unsealed only after a hypothesis is
    frozen and only if it was not used during discovery.
    """
    if frozen.state != (
        HypothesisState.FROZEN
    ):
        raise PermissionError(
            "cannot unseal validation data "
            "before hypothesis freeze"
        )

    if dataset.role != (
        DatasetRole.VALIDATION
    ):
        raise PermissionError(
            "only validation data may be "
            "unsealed here"
        )

    if dataset.dataset_id in (
        frozen.specification
        .discovery_dataset_ids
    ):
        raise PermissionError(
            "dataset already participated "
            "in discovery"
        )

    return DataDeclaration(
        dataset_id=dataset.dataset_id,
        role=dataset.role,
        sealed=False,
    )


def validate_evidence_identity(
    frozen: FrozenHypothesis,
    evidence: ValidationEvidence,
) -> None:
    if (
        evidence.hypothesis_id
        != frozen.hypothesis_id
    ):
        raise ValueError(
            "validation evidence belongs "
            "to another hypothesis"
        )

    if (
        evidence.specification_hash
        != frozen.specification_hash
    ):
        raise ValueError(
            "frozen specification changed"
        )


def judge_validation(
    frozen: FrozenHypothesis,
    dataset: DataDeclaration,
    evidence: ValidationEvidence,
    *,
    policy: ValidationPolicy = (
        ValidationPolicy()
    ),
) -> ValidationDecision:
    assert_validation_access(
        frozen,
        dataset,
    )

    validate_evidence_identity(
        frozen,
        evidence,
    )

    if (
        evidence.dataset_id
        != dataset.dataset_id
    ):
        raise ValueError(
            "evidence dataset does not "
            "match validation dataset"
        )

    spec = frozen.specification

    reasons = []

    if (
        evidence.n_samples
        < spec.min_samples
    ):
        reasons.append(
            "insufficient_samples"
        )

    if (
        evidence.n_events
        < spec.min_events
    ):
        reasons.append(
            "insufficient_events"
        )

    if (
        abs(evidence.primary_effect)
        < policy.min_abs_effect
    ):
        reasons.append(
            "effect_too_small"
        )

    if (
        policy.max_adjusted_p_value
        is not None
    ):
        if (
            evidence.adjusted_p_value
            is None
            or evidence.adjusted_p_value
            > policy.max_adjusted_p_value
        ):
            reasons.append(
                "multiple_testing_failure"
            )

    if (
        evidence.symbol_concentration
        > policy.max_symbol_concentration
    ):
        reasons.append(
            "symbol_concentration"
        )

    if (
        evidence.time_concentration
        > policy.max_time_concentration
    ):
        reasons.append(
            "time_concentration"
        )

    if (
        evidence.parameter_stability
        < policy.min_parameter_stability
    ):
        reasons.append(
            "parameter_instability"
        )

    if (
        evidence.effective_sample_size
        is not None
        and evidence.effective_sample_size
        < policy.min_effective_sample_size
    ):
        reasons.append(
            "insufficient_effective_sample"
        )

    if (
        policy.require_positive_net_effect
        and evidence.net_effect is not None
    ):
        expected_direction = (
            spec.direction
        )

        if expected_direction is None:
            if abs(evidence.net_effect) <= 0.0:
                reasons.append(
                    "cost_failure"
                )
        elif (
            evidence.net_effect
            * expected_direction
            <= 0.0
        ):
            reasons.append(
                "cost_failure"
            )

    state = (
        HypothesisState.VALIDATED_PASS
        if not reasons
        else HypothesisState.VALIDATED_FAIL
    )

    return ValidationDecision(
        hypothesis_id=(
            frozen.hypothesis_id
        ),
        dataset_id=(
            dataset.dataset_id
        ),
        state=state,
        reasons=tuple(reasons),
    )
