"""
Transactional execution of one sealed validation batch.

The executor is deliberately dependency-injected so lifecycle mechanics
can be tested without touching a real validation resource.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path


def _jsonable(value):
    if is_dataclass(value):
        return {
            key: _jsonable(item)
            for key, item
            in asdict(value).items()
        }

    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _jsonable(item)
            for item in value
        ]

    return value


def atomic_write_json(
    path: Path,
    payload,
):
    path = Path(path)

    tmp = path.with_name(
        path.name + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            _jsonable(payload),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    os.replace(tmp, path)


def execute_sealed_batch(
    *,
    controller,
    batch,
    frozen,
    load_rows,
    validate,
    report_path: Path,
):
    """
    Execute an already-preflighted sealed batch.

    Ordering is intentional:

      grants
      -> record access for every frozen member
      -> physical dataset load exactly once
      -> evaluate all members
      -> persist complete report atomically
      -> finalize / mark validation dataset spent

    Once access is recorded, a failed execution is contaminated and must
    never be treated as pristine validation again.
    """

    frozen = tuple(frozen)

    grants = controller.grant_validation_batch(
        batch.batch_id,
        frozen,
    )

    if len(grants) != len(frozen):
        raise RuntimeError(
            "grant/member count mismatch"
        )

    accesses = []

    for grant, hypothesis in zip(
        grants,
        frozen,
    ):
        accesses.append(
            controller.validation_batch_access(
                batch.batch_id,
                grant,
                hypothesis,
            )
        )

    resource_ids = {
        access.resource_id
        for access in accesses
    }

    if len(resource_ids) != 1:
        raise RuntimeError(
            "validation batch members "
            "resolved to different resources"
        )

    resource_id = next(
        iter(resource_ids)
    )

    rows = load_rows(resource_id)

    results = []

    for hypothesis in frozen:
        result = validate(
            hypothesis,
            rows,
        )

        results.append({
            "hypothesis_id":
                hypothesis.hypothesis_id,
            "specification_hash":
                hypothesis.specification_hash,
            "scientist":
                hypothesis.specification.scientist,
            "tests_considered":
                hypothesis.specification.tests_considered,
            "result":
                _jsonable(result),
        })

    if len(results) != len(frozen):
        raise RuntimeError(
            "incomplete validation results"
        )

    report = {
        "batch_id": batch.batch_id,
        "dataset_id": batch.dataset_id,
        "manifest_hash":
            batch.manifest_hash,
        "member_count":
            len(frozen),
        "results":
            results,
        "complete":
            True,
        "finalized":
            False,
    }

    # The complete evidence is durable BEFORE spending/finalizing.
    atomic_write_json(
        report_path,
        report,
    )

    finalized = (
        controller.finalize_validation_batch(
            batch.batch_id
        )
    )

    report["finalized"] = True
    report["dataset_spent"] = (
        controller.validation_dataset_spent(
            batch.dataset_id
        )
    )

    # Safe post-finalization rewrite of already-durable evidence.
    atomic_write_json(
        report_path,
        report,
    )

    return report, finalized
