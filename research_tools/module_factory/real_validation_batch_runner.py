"""
One-shot real validation runner for a sealed Module Factory batch.

PRE-FLIGHT mode is deliberately incapable of opening validation data.
It verifies durable identity and sealed membership only.

Actual validation execution will be added only after pre-flight is
covered by tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_tools.module_factory.dataset_lifecycle import (
    DatasetLifecycleController,
)
from research_tools.module_factory.hypothesis_protocol import (
    freeze_hypothesis,
    make_specification,
)
from research_tools.module_factory.real_datasets import (
    SEP02_DATASET_ID,
    dataset_declarations,
)


DEFAULT_MANIFEST = Path(
    "research_data/factory_validation_batch_001.json"
)

DEFAULT_STATE = Path(
    "research_data/factory_validation_lifecycle.json"
)


def _parameters(value):
    if isinstance(value, dict):
        return dict(value)

    return {
        str(name): item
        for name, item in value
    }


def reconstruct_frozen(item):
    payload = item["specification"]

    spec = make_specification(
        scientist=payload["scientist"],
        discovery_id=payload["discovery_id"],
        target=payload["target"],
        horizon=int(payload["horizon"]),
        features=tuple(payload["features"]),
        parameters=_parameters(
            payload.get("parameters", ())
        ),
        direction=payload.get("direction"),
        ancestry=tuple(
            payload.get("ancestry", ())
        ),
        provenance=tuple(
            payload.get("provenance", ())
        ),
        discovery_dataset_ids=tuple(
            payload.get(
                "discovery_dataset_ids",
                (),
            )
        ),
        multiple_testing_family=(
            payload["multiple_testing_family"]
        ),
        tests_considered=int(
            payload["tests_considered"]
        ),
        min_samples=int(
            payload["min_samples"]
        ),
        min_events=int(
            payload.get("min_events", 0)
        ),
    )

    frozen = freeze_hypothesis(spec)

    if (
        frozen.hypothesis_id
        != item["hypothesis_id"]
    ):
        raise RuntimeError(
            "manifest hypothesis identity mismatch: "
            f"{item['hypothesis_id']} != "
            f"{frozen.hypothesis_id}"
        )

    if (
        frozen.specification_hash
        != item["specification_hash"]
    ):
        raise RuntimeError(
            "manifest specification hash mismatch: "
            f"{item['hypothesis_id']}"
        )

    return frozen


def load_preflight(
    *,
    root: Path,
    manifest_path: Path,
    state_path: Path,
):
    manifest = json.loads(
        manifest_path.read_text()
    )

    if manifest["dataset_id"] != SEP02_DATASET_ID:
        raise RuntimeError(
            "unexpected validation dataset: "
            f"{manifest['dataset_id']}"
        )

    if manifest.get("finalized"):
        raise RuntimeError(
            "manifest says validation batch is finalized"
        )

    frozen = tuple(
        reconstruct_frozen(item)
        for item in manifest["hypotheses"]
    )

    if not frozen:
        raise RuntimeError(
            "validation batch has no hypotheses"
        )

    if len({
        item.hypothesis_id
        for item in frozen
    }) != len(frozen):
        raise RuntimeError(
            "duplicate hypothesis in manifest"
        )

    controller = DatasetLifecycleController(
        state_path=state_path
    )

    controller.register_many(
        dataset_declarations(root)
    )

    batch = controller.validation_batch(
        manifest["batch_id"]
    )

    if batch.dataset_id != SEP02_DATASET_ID:
        raise RuntimeError(
            "sealed batch dataset mismatch"
        )

    if (
        batch.manifest_hash
        != manifest["manifest_hash"]
    ):
        raise RuntimeError(
            "sealed batch manifest hash mismatch"
        )

    expected_ids = tuple(sorted(
        item.hypothesis_id
        for item in frozen
    ))

    expected_hashes = tuple(
        item.specification_hash
        for item in sorted(
            frozen,
            key=lambda item:
                item.hypothesis_id,
        )
    )

    if batch.hypothesis_ids != expected_ids:
        raise RuntimeError(
            "sealed hypothesis membership mismatch"
        )

    if (
        batch.specification_hashes
        != expected_hashes
    ):
        raise RuntimeError(
            "sealed specification membership mismatch"
        )

    if batch.finalized:
        raise RuntimeError(
            "sealed batch is already finalized"
        )

    if controller.validation_dataset_spent(
        SEP02_DATASET_ID
    ):
        raise RuntimeError(
            "Sep2 validation dataset is already spent"
        )

    return manifest, frozen, controller, batch


def preflight(
    *,
    root: Path,
    manifest_path: Path,
    state_path: Path,
):
    (
        manifest,
        frozen,
        controller,
        batch,
    ) = load_preflight(
        root=root,
        manifest_path=manifest_path,
        state_path=state_path,
    )

    print("PREFLIGHT_OK", True)
    print("BATCH_ID", batch.batch_id)
    print("MANIFEST_HASH", batch.manifest_hash)
    print("MEMBERS", len(frozen))
    print("FINALIZED", batch.finalized)
    print(
        "SEP02_SPENT",
        controller.validation_dataset_spent(
            SEP02_DATASET_ID
        ),
    )
    print("VALIDATION_GRANTS_CREATED", 0)
    print("SEP02_CONTENT_OPENED", False)

    for index, item in enumerate(
        frozen,
        1,
    ):
        print(
            index,
            item.specification.scientist,
            item.hypothesis_id,
            item.specification_hash[:16],
        )

    return manifest


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--preflight",
        action="store_true",
        required=True,
        help=(
            "verify sealed identities only; "
            "does not access validation data"
        ),
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )

    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE,
    )

    args = parser.parse_args()

    root = Path(".").resolve()

    preflight(
        root=root,
        manifest_path=args.manifest.resolve(),
        state_path=args.state.resolve(),
    )


if __name__ == "__main__":
    main()
