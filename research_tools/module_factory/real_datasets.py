"""
Real Module Factory dataset declarations.

Scientific firewall
-------------------
2026-08-28:
    DISCOVERY
    Available to autonomous research.

2026-09-02:
    VALIDATION
    SEALED.
    Must not be read by discovery machinery.

This module declares resource identities only.
It does not open, decompress, parse, hash, or inspect dataset contents.
"""

from __future__ import annotations

from pathlib import Path

from research_tools.module_factory.dataset_lifecycle import (
    DatasetLifecycleController,
    RegisteredDataset,
)
from research_tools.module_factory.hypothesis_protocol import (
    DatasetRole,
)


AUG28_DATASET_ID = "market-quotes:2026-08-28"
SEP02_DATASET_ID = "market-quotes:2026-09-02"

AUG28_RELATIVE_PATH = (
    "diagnostics/2026-08-28/"
    "minute_market_quotes_20260828.csv.gz"
)

SEP02_RELATIVE_PATH = (
    "research_data/"
    "minute_market_quotes_20260902.csv.gz"
)


def dataset_declarations(
    repo_root: str | Path,
) -> tuple[
    RegisteredDataset,
    RegisteredDataset,
]:
    root = Path(
        repo_root
    ).resolve()

    aug28 = (
        root
        / AUG28_RELATIVE_PATH
    )

    sep02 = (
        root
        / SEP02_RELATIVE_PATH
    )

    return (
        RegisteredDataset(
            dataset_id=(
                AUG28_DATASET_ID
            ),
            role=(
                DatasetRole.DISCOVERY
            ),
            resource_id=str(
                aug28
            ),
            sealed=False,
        ),
        RegisteredDataset(
            dataset_id=(
                SEP02_DATASET_ID
            ),
            role=(
                DatasetRole.VALIDATION
            ),
            resource_id=str(
                sep02
            ),
            sealed=True,
        ),
    )


def build_real_dataset_controller(
    repo_root: str | Path,
) -> DatasetLifecycleController:
    controller = (
        DatasetLifecycleController()
    )

    controller.register_many(
        dataset_declarations(
            repo_root
        )
    )

    return controller


def verify_resource_metadata(
    dataset: RegisteredDataset,
) -> dict[str, object]:
    """
    Check filesystem metadata only.

    IMPORTANT:
    No file open(), gzip access, hashing, parsing, or content reads.
    """
    path = Path(
        dataset.resource_id
    )

    return {
        "dataset_id":
            dataset.dataset_id,
        "role":
            dataset.role.value,
        "sealed":
            dataset.sealed,
        "path":
            str(path),
        "exists":
            path.exists(),
        "is_file":
            path.is_file(),
    }


def verify_real_dataset_metadata(
    repo_root: str | Path,
) -> tuple[
    dict[str, object],
    ...
]:
    return tuple(
        verify_resource_metadata(
            dataset
        )
        for dataset
        in dataset_declarations(
            repo_root
        )
    )
