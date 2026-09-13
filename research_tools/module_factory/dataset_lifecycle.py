"""
Dataset lifecycle and access firewall for Module Factory.

Scientific invariant
--------------------
Discovery datasets may be accessed by discovery machinery.

Validation datasets remain sealed until an exact hypothesis has been
frozen. Validation access is granted to that exact hypothesis identity
and specification hash only.

Opening validation data for hypothesis A does NOT expose it to
hypothesis B.

This module manages declarations, grants, and audit events. It does not
load market data itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from research_tools.module_factory.hypothesis_protocol import (
    DatasetRole,
    FrozenHypothesis,
    HypothesisState,
)


class AccessPurpose(str, Enum):
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"


class AuditAction(str, Enum):
    REGISTER = "REGISTER"
    DISCOVERY_ACCESS = "DISCOVERY_ACCESS"
    VALIDATION_GRANT = "VALIDATION_GRANT"
    VALIDATION_ACCESS = "VALIDATION_ACCESS"
    ACCESS_DENIED = "ACCESS_DENIED"


@dataclass(frozen=True)
class RegisteredDataset:
    dataset_id: str
    role: DatasetRole
    resource_id: str
    sealed: bool

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError(
                "dataset_id cannot be empty"
            )

        if not self.resource_id.strip():
            raise ValueError(
                "resource_id cannot be empty"
            )

        if (
            self.role == DatasetRole.VALIDATION
            and not self.sealed
        ):
            raise ValueError(
                "validation datasets must be "
                "registered sealed"
            )


@dataclass(frozen=True)
class ValidationGrant:
    grant_id: str
    dataset_id: str
    hypothesis_id: str
    specification_hash: str
    purpose: AccessPurpose = (
        AccessPurpose.VALIDATION
    )


@dataclass(frozen=True)
class ValidationBatch:
    batch_id: str
    dataset_id: str
    manifest_hash: str
    hypothesis_ids: tuple[str, ...]
    specification_hashes: tuple[str, ...]
    finalized: bool = False


@dataclass(frozen=True)
class DatasetAccess:
    dataset_id: str
    resource_id: str
    purpose: AccessPurpose
    hypothesis_id: str | None = None
    specification_hash: str | None = None
    grant_id: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    action: AuditAction
    dataset_id: str
    purpose: AccessPurpose | None
    hypothesis_id: str | None
    specification_hash: str | None
    grant_id: str | None
    detail: str


def _grant_id(
    *,
    dataset_id: str,
    hypothesis_id: str,
    specification_hash: str,
) -> str:
    payload = json.dumps(
        {
            "dataset_id":
                dataset_id,
            "hypothesis_id":
                hypothesis_id,
            "specification_hash":
                specification_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        payload.encode()
    ).hexdigest()[:20]

    return f"grant:{digest}"


def _batch_manifest(
    *,
    dataset_id: str,
    frozen_hypotheses: Iterable[FrozenHypothesis],
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
]:
    members = []

    for frozen in frozen_hypotheses:
        if frozen.state != HypothesisState.FROZEN:
            raise PermissionError(
                "validation batch requires "
                "frozen hypotheses"
            )

        members.append(
            (
                frozen.hypothesis_id,
                frozen.specification_hash,
            )
        )

    if not members:
        raise ValueError(
            "validation batch cannot be empty"
        )

    if len(
        {hypothesis_id for hypothesis_id, _ in members}
    ) != len(members):
        raise ValueError(
            "validation batch hypotheses "
            "must be unique"
        )

    members = sorted(members)

    payload = json.dumps(
        {
            "dataset_id": dataset_id,
            "members": members,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    manifest_hash = hashlib.sha256(
        payload.encode()
    ).hexdigest()

    hypothesis_ids = tuple(
        hypothesis_id
        for hypothesis_id, _
        in members
    )

    specification_hashes = tuple(
        specification_hash
        for _, specification_hash
        in members
    )

    return (
        manifest_hash,
        hypothesis_ids,
        specification_hashes,
    )


def _batch_id(
    *,
    dataset_id: str,
    manifest_hash: str,
) -> str:
    payload = json.dumps(
        {
            "dataset_id": dataset_id,
            "manifest_hash": manifest_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        payload.encode()
    ).hexdigest()[:20]

    return f"validation-batch:{digest}"


class DatasetLifecycleController:
    def __init__(
        self,
        state_path=None,
    ) -> None:
        self._datasets: dict[
            str,
            RegisteredDataset,
        ] = {}

        self._grants: dict[
            str,
            ValidationGrant,
        ] = {}

        self._audit: list[
            AuditEvent
        ] = []

        self._validation_batches: dict[
            str,
            ValidationBatch,
        ] = {}

        self._superseded_validation_batches: dict[
            str,
            ValidationBatch,
        ] = {}

        self._spent_validation_datasets: set[
            str
        ] = set()

        self._batch_accessed_hypotheses: dict[
            str,
            set[str],
        ] = {}

        self.state_path = (
            None
            if state_path is None
            else __import__("pathlib").Path(state_path)
        )

        self._load_state()

    def _load_state(self) -> None:
        if self.state_path is None:
            return

        if not self.state_path.exists():
            return

        payload = json.loads(
            self.state_path.read_text()
        )

        if payload.get("version") != 1:
            raise RuntimeError(
                "Unsupported dataset lifecycle "
                "state version"
            )

        batches = payload.get(
            "validation_batches",
            []
        )

        if not isinstance(batches, list):
            raise RuntimeError(
                "Invalid validation batch state"
            )

        restored_batches = {}

        for item in batches:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "Invalid validation batch entry"
                )

            batch = ValidationBatch(
                batch_id=str(item["batch_id"]),
                dataset_id=str(item["dataset_id"]),
                manifest_hash=str(
                    item["manifest_hash"]
                ),
                hypothesis_ids=tuple(
                    str(value)
                    for value
                    in item["hypothesis_ids"]
                ),
                specification_hashes=tuple(
                    str(value)
                    for value
                    in item[
                        "specification_hashes"
                    ]
                ),
                finalized=bool(
                    item.get("finalized", False)
                ),
            )

            restored_batches[
                batch.batch_id
            ] = batch

        superseded = payload.get(
            "superseded_validation_batches",
            []
        )

        if not isinstance(superseded, list):
            raise RuntimeError(
                "Invalid superseded validation batch state"
            )

        restored_superseded = {}

        for item in superseded:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "Invalid superseded validation batch entry"
                )

            batch = ValidationBatch(
                batch_id=str(item["batch_id"]),
                dataset_id=str(item["dataset_id"]),
                manifest_hash=str(
                    item["manifest_hash"]
                ),
                hypothesis_ids=tuple(
                    str(value)
                    for value in item["hypothesis_ids"]
                ),
                specification_hashes=tuple(
                    str(value)
                    for value in item[
                        "specification_hashes"
                    ]
                ),
                finalized=bool(
                    item.get("finalized", False)
                ),
            )

            restored_superseded[
                batch.batch_id
            ] = batch

        spent = payload.get(
            "spent_validation_datasets",
            []
        )

        accessed = payload.get(
            "batch_accessed_hypotheses",
            {}
        )

        if not isinstance(spent, list):
            raise RuntimeError(
                "Invalid spent dataset state"
            )

        if not isinstance(accessed, dict):
            raise RuntimeError(
                "Invalid batch access state"
            )

        self._validation_batches = (
            restored_batches
        )

        self._superseded_validation_batches = (
            restored_superseded
        )

        self._spent_validation_datasets = {
            str(dataset_id)
            for dataset_id in spent
        }

        self._batch_accessed_hypotheses = {
            str(batch_id): {
                str(hypothesis_id)
                for hypothesis_id
                in hypothesis_ids
            }
            for batch_id, hypothesis_ids
            in accessed.items()
        }

    def _save_state(self) -> None:
        if self.state_path is None:
            return

        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )

        payload = {
            "version": 1,
            "validation_batches": [
                {
                    "batch_id": batch.batch_id,
                    "dataset_id": batch.dataset_id,
                    "manifest_hash":
                        batch.manifest_hash,
                    "hypothesis_ids":
                        list(batch.hypothesis_ids),
                    "specification_hashes":
                        list(
                            batch.specification_hashes
                        ),
                    "finalized":
                        batch.finalized,
                }
                for batch in sorted(
                    self._validation_batches.values(),
                    key=lambda value: value.batch_id,
                )
            ],
            "superseded_validation_batches": [
                {
                    "batch_id": batch.batch_id,
                    "dataset_id": batch.dataset_id,
                    "manifest_hash":
                        batch.manifest_hash,
                    "hypothesis_ids":
                        list(batch.hypothesis_ids),
                    "specification_hashes":
                        list(
                            batch.specification_hashes
                        ),
                    "finalized":
                        batch.finalized,
                }
                for batch in sorted(
                    self._superseded_validation_batches.values(),
                    key=lambda value: value.batch_id,
                )
            ],
            "spent_validation_datasets":
                sorted(
                    self._spent_validation_datasets
                ),
            "batch_accessed_hypotheses": {
                batch_id: sorted(
                    hypothesis_ids
                )
                for batch_id, hypothesis_ids
                in sorted(
                    self._batch_accessed_hypotheses.items()
                )
            },
        }

        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        temporary.replace(
            self.state_path
        )

    def _record(
        self,
        *,
        action: AuditAction,
        dataset_id: str,
        purpose: (
            AccessPurpose | None
        ),
        hypothesis_id: str | None,
        specification_hash: (
            str | None
        ),
        grant_id: str | None,
        detail: str,
    ) -> None:
        self._audit.append(
            AuditEvent(
                sequence=(
                    len(self._audit)
                    + 1
                ),
                action=action,
                dataset_id=dataset_id,
                purpose=purpose,
                hypothesis_id=(
                    hypothesis_id
                ),
                specification_hash=(
                    specification_hash
                ),
                grant_id=grant_id,
                detail=detail,
            )
        )

    def register(
        self,
        dataset: RegisteredDataset,
    ) -> None:
        existing = self._datasets.get(
            dataset.dataset_id
        )

        if existing is not None:
            if existing == dataset:
                return

            raise ValueError(
                "dataset_id already registered "
                "with different declaration"
            )

        self._datasets[
            dataset.dataset_id
        ] = dataset

        self._record(
            action=AuditAction.REGISTER,
            dataset_id=dataset.dataset_id,
            purpose=None,
            hypothesis_id=None,
            specification_hash=None,
            grant_id=None,
            detail=(
                f"role={dataset.role.value};"
                f"sealed={dataset.sealed}"
            ),
        )

    def register_many(
        self,
        datasets: Iterable[
            RegisteredDataset
        ],
    ) -> None:
        for dataset in datasets:
            self.register(dataset)

    def dataset(
        self,
        dataset_id: str,
    ) -> RegisteredDataset:
        try:
            return self._datasets[
                dataset_id
            ]
        except KeyError as exc:
            raise KeyError(
                f"unknown dataset: "
                f"{dataset_id}"
            ) from exc

    def discovery_access(
        self,
        dataset_id: str,
    ) -> DatasetAccess:
        dataset = self.dataset(
            dataset_id
        )

        if (
            dataset.role
            != DatasetRole.DISCOVERY
        ):
            self._record(
                action=(
                    AuditAction.ACCESS_DENIED
                ),
                dataset_id=dataset_id,
                purpose=(
                    AccessPurpose.DISCOVERY
                ),
                hypothesis_id=None,
                specification_hash=None,
                grant_id=None,
                detail=(
                    "dataset is not a "
                    "discovery dataset"
                ),
            )

            raise PermissionError(
                "validation dataset cannot "
                "be accessed for discovery"
            )

        self._record(
            action=(
                AuditAction.DISCOVERY_ACCESS
            ),
            dataset_id=dataset_id,
            purpose=(
                AccessPurpose.DISCOVERY
            ),
            hypothesis_id=None,
            specification_hash=None,
            grant_id=None,
            detail=(
                "discovery access granted"
            ),
        )

        return DatasetAccess(
            dataset_id=dataset.dataset_id,
            resource_id=dataset.resource_id,
            purpose=(
                AccessPurpose.DISCOVERY
            ),
        )

    def grant_validation(
        self,
        dataset_id: str,
        frozen: FrozenHypothesis,
    ) -> ValidationGrant:
        dataset = self.dataset(
            dataset_id
        )

        if dataset_id in self._spent_validation_datasets:
            self._record(
                action=AuditAction.ACCESS_DENIED,
                dataset_id=dataset_id,
                purpose=AccessPurpose.VALIDATION,
                hypothesis_id=frozen.hypothesis_id,
                specification_hash=(
                    frozen.specification_hash
                ),
                grant_id=None,
                detail=(
                    "validation dataset is spent"
                ),
            )

            raise PermissionError(
                "validation dataset is spent"
            )

        if (
            dataset.role
            != DatasetRole.VALIDATION
        ):
            self._record(
                action=(
                    AuditAction.ACCESS_DENIED
                ),
                dataset_id=dataset_id,
                purpose=(
                    AccessPurpose.VALIDATION
                ),
                hypothesis_id=(
                    frozen.hypothesis_id
                ),
                specification_hash=(
                    frozen.specification_hash
                ),
                grant_id=None,
                detail=(
                    "dataset is not a "
                    "validation dataset"
                ),
            )

            raise PermissionError(
                "validation grants require "
                "a validation dataset"
            )

        if (
            frozen.state
            != HypothesisState.FROZEN
        ):
            raise PermissionError(
                "validation access requires "
                "a frozen hypothesis"
            )

        if (
            dataset_id
            in frozen.specification
            .discovery_dataset_ids
        ):
            self._record(
                action=(
                    AuditAction.ACCESS_DENIED
                ),
                dataset_id=dataset_id,
                purpose=(
                    AccessPurpose.VALIDATION
                ),
                hypothesis_id=(
                    frozen.hypothesis_id
                ),
                specification_hash=(
                    frozen.specification_hash
                ),
                grant_id=None,
                detail=(
                    "dataset participated "
                    "in discovery"
                ),
            )

            raise PermissionError(
                "discovery data cannot become "
                "unseen validation"
            )

        grant_id = _grant_id(
            dataset_id=dataset_id,
            hypothesis_id=(
                frozen.hypothesis_id
            ),
            specification_hash=(
                frozen.specification_hash
            ),
        )

        grant = ValidationGrant(
            grant_id=grant_id,
            dataset_id=dataset_id,
            hypothesis_id=(
                frozen.hypothesis_id
            ),
            specification_hash=(
                frozen.specification_hash
            ),
        )

        self._grants[
            grant_id
        ] = grant

        self._record(
            action=(
                AuditAction.VALIDATION_GRANT
            ),
            dataset_id=dataset_id,
            purpose=(
                AccessPurpose.VALIDATION
            ),
            hypothesis_id=(
                frozen.hypothesis_id
            ),
            specification_hash=(
                frozen.specification_hash
            ),
            grant_id=grant_id,
            detail=(
                "hypothesis-scoped "
                "validation grant created"
            ),
        )

        return grant

    def create_validation_batch(
        self,
        dataset_id: str,
        frozen_hypotheses: Iterable[
            FrozenHypothesis
        ],
    ) -> ValidationBatch:
        dataset = self.dataset(dataset_id)

        if dataset.role != DatasetRole.VALIDATION:
            raise PermissionError(
                "validation batch requires "
                "a validation dataset"
            )

        if (
            dataset_id
            in self._spent_validation_datasets
        ):
            raise PermissionError(
                "validation dataset is spent"
            )

        frozen_hypotheses = tuple(
            frozen_hypotheses
        )

        (
            manifest_hash,
            hypothesis_ids,
            specification_hashes,
        ) = _batch_manifest(
            dataset_id=dataset_id,
            frozen_hypotheses=frozen_hypotheses,
        )

        batch_id = _batch_id(
            dataset_id=dataset_id,
            manifest_hash=manifest_hash,
        )

        batch = ValidationBatch(
            batch_id=batch_id,
            dataset_id=dataset_id,
            manifest_hash=manifest_hash,
            hypothesis_ids=hypothesis_ids,
            specification_hashes=(
                specification_hashes
            ),
        )

        existing = self._validation_batches.get(
            batch_id
        )

        if existing is not None:
            if existing != batch:
                raise RuntimeError(
                    "validation batch identity "
                    "collision"
                )

            return existing

        # Only one sealed batch may claim a pristine
        # validation dataset.
        for other in self._validation_batches.values():
            if other.dataset_id == dataset_id:
                raise PermissionError(
                    "validation dataset already "
                    "has a sealed batch"
                )

        self._validation_batches[
            batch_id
        ] = batch

        self._batch_accessed_hypotheses[
            batch_id
        ] = set()

        self._save_state()

        return batch

    def supersede_validation_batch(
        self,
        batch_id: str,
    ) -> ValidationBatch:
        """
        Retire an untouched sealed validation batch.

        This is permitted only before any member has accessed the
        validation dataset. The dataset therefore remains pristine.

        Any process-local grants for the retired members are revoked.
        The old batch is retained durably as a tombstone.
        """
        batch = self.validation_batch(batch_id)

        if batch.finalized:
            raise PermissionError(
                "finalized validation batch "
                "cannot be superseded"
            )

        if (
            batch.dataset_id
            in self._spent_validation_datasets
        ):
            raise PermissionError(
                "spent validation dataset "
                "cannot be superseded"
            )

        accessed = (
            self._batch_accessed_hypotheses.get(
                batch_id,
                set(),
            )
        )

        if accessed:
            raise PermissionError(
                "validation batch cannot be "
                "superseded after validation access"
            )

        member_ids = set(
            batch.hypothesis_ids
        )

        revoked_grant_ids = [
            grant_id
            for grant_id, grant
            in self._grants.items()
            if (
                grant.dataset_id
                == batch.dataset_id
                and grant.hypothesis_id
                in member_ids
            )
        ]

        for grant_id in revoked_grant_ids:
            del self._grants[grant_id]

        del self._validation_batches[
            batch_id
        ]

        self._batch_accessed_hypotheses.pop(
            batch_id,
            None,
        )

        self._superseded_validation_batches[
            batch_id
        ] = batch

        self._save_state()

        return batch

    def validation_batch(
        self,
        batch_id: str,
    ) -> ValidationBatch:
        try:
            return self._validation_batches[
                batch_id
            ]
        except KeyError as exc:
            raise KeyError(
                f"unknown validation batch: "
                f"{batch_id}"
            ) from exc

    def grant_validation_batch(
        self,
        batch_id: str,
        frozen_hypotheses: Iterable[
            FrozenHypothesis
        ],
    ) -> tuple[ValidationGrant, ...]:
        batch = self.validation_batch(batch_id)

        if batch.finalized:
            raise PermissionError(
                "validation batch is finalized"
            )

        if (
            batch.dataset_id
            in self._spent_validation_datasets
        ):
            raise PermissionError(
                "validation dataset is spent"
            )

        frozen_hypotheses = tuple(
            frozen_hypotheses
        )

        (
            manifest_hash,
            hypothesis_ids,
            specification_hashes,
        ) = _batch_manifest(
            dataset_id=batch.dataset_id,
            frozen_hypotheses=frozen_hypotheses,
        )

        if (
            manifest_hash != batch.manifest_hash
            or hypothesis_ids
            != batch.hypothesis_ids
            or specification_hashes
            != batch.specification_hashes
        ):
            raise PermissionError(
                "validation batch membership "
                "is sealed"
            )

        return tuple(
            self.grant_validation(
                batch.dataset_id,
                frozen,
            )
            for frozen in frozen_hypotheses
        )

    def validation_batch_access(
        self,
        batch_id: str,
        grant: ValidationGrant,
        frozen: FrozenHypothesis,
    ) -> DatasetAccess:
        batch = self.validation_batch(batch_id)

        if batch.finalized:
            raise PermissionError(
                "validation batch is finalized"
            )

        if (
            frozen.hypothesis_id
            not in batch.hypothesis_ids
        ):
            raise PermissionError(
                "hypothesis is not a member "
                "of validation batch"
            )

        member_index = (
            batch.hypothesis_ids.index(
                frozen.hypothesis_id
            )
        )

        expected_hash = (
            batch.specification_hashes[
                member_index
            ]
        )

        if (
            frozen.specification_hash
            != expected_hash
        ):
            raise PermissionError(
                "hypothesis specification "
                "does not match batch manifest"
            )

        if (
            grant.dataset_id
            != batch.dataset_id
        ):
            raise PermissionError(
                "grant dataset does not match "
                "validation batch"
            )

        access = self.validation_access(
            grant,
            frozen,
        )

        self._batch_accessed_hypotheses.setdefault(
            batch_id,
            set(),
        ).add(
            frozen.hypothesis_id
        )

        self._save_state()

        return access

    def finalize_validation_batch(
        self,
        batch_id: str,
    ) -> ValidationBatch:
        batch = self.validation_batch(batch_id)

        if batch.finalized:
            return batch

        accessed = (
            self._batch_accessed_hypotheses.get(
                batch_id,
                set(),
            )
        )

        required = set(
            batch.hypothesis_ids
        )

        if accessed != required:
            raise PermissionError(
                "validation batch cannot be "
                "finalized before every member "
                "has accessed validation"
            )

        finalized = ValidationBatch(
            batch_id=batch.batch_id,
            dataset_id=batch.dataset_id,
            manifest_hash=batch.manifest_hash,
            hypothesis_ids=batch.hypothesis_ids,
            specification_hashes=(
                batch.specification_hashes
            ),
            finalized=True,
        )

        self._validation_batches[
            batch_id
        ] = finalized

        self._spent_validation_datasets.add(
            batch.dataset_id
        )

        self._save_state()

        return finalized

    def validation_dataset_spent(
        self,
        dataset_id: str,
    ) -> bool:
        self.dataset(dataset_id)

        return (
            dataset_id
            in self._spent_validation_datasets
        )

    def validation_access(
        self,
        grant: ValidationGrant,
        frozen: FrozenHypothesis,
    ) -> DatasetAccess:
        stored = self._grants.get(
            grant.grant_id
        )

        if stored != grant:
            self._record(
                action=(
                    AuditAction.ACCESS_DENIED
                ),
                dataset_id=(
                    grant.dataset_id
                ),
                purpose=(
                    AccessPurpose.VALIDATION
                ),
                hypothesis_id=(
                    frozen.hypothesis_id
                ),
                specification_hash=(
                    frozen.specification_hash
                ),
                grant_id=grant.grant_id,
                detail=(
                    "unknown or forged grant"
                ),
            )

            raise PermissionError(
                "unknown validation grant"
            )

        if (
            frozen.state
            != HypothesisState.FROZEN
        ):
            raise PermissionError(
                "hypothesis is not frozen"
            )

        if (
            grant.hypothesis_id
            != frozen.hypothesis_id
            or grant.specification_hash
            != frozen.specification_hash
        ):
            self._record(
                action=(
                    AuditAction.ACCESS_DENIED
                ),
                dataset_id=(
                    grant.dataset_id
                ),
                purpose=(
                    AccessPurpose.VALIDATION
                ),
                hypothesis_id=(
                    frozen.hypothesis_id
                ),
                specification_hash=(
                    frozen.specification_hash
                ),
                grant_id=grant.grant_id,
                detail=(
                    "grant belongs to another "
                    "frozen hypothesis"
                ),
            )

            raise PermissionError(
                "validation grant is scoped "
                "to another hypothesis"
            )

        dataset = self.dataset(
            grant.dataset_id
        )

        if (
            dataset.role
            != DatasetRole.VALIDATION
        ):
            raise PermissionError(
                "grant target is not "
                "validation data"
            )

        self._record(
            action=(
                AuditAction.VALIDATION_ACCESS
            ),
            dataset_id=(
                dataset.dataset_id
            ),
            purpose=(
                AccessPurpose.VALIDATION
            ),
            hypothesis_id=(
                frozen.hypothesis_id
            ),
            specification_hash=(
                frozen.specification_hash
            ),
            grant_id=grant.grant_id,
            detail=(
                "validation resource access "
                "granted to exact hypothesis"
            ),
        )

        return DatasetAccess(
            dataset_id=(
                dataset.dataset_id
            ),
            resource_id=(
                dataset.resource_id
            ),
            purpose=(
                AccessPurpose.VALIDATION
            ),
            hypothesis_id=(
                frozen.hypothesis_id
            ),
            specification_hash=(
                frozen.specification_hash
            ),
            grant_id=(
                grant.grant_id
            ),
        )

    def audit_log(
        self,
    ) -> tuple[AuditEvent, ...]:
        return tuple(
            self._audit
        )

    def grants(
        self,
    ) -> tuple[
        ValidationGrant,
        ...
    ]:
        return tuple(
            self._grants.values()
        )
