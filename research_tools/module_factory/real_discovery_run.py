"""
First real autonomous Module Factory discovery run.

DATA POLICY
-----------
Reads only a DatasetLifecycleController-authorized DISCOVERY dataset.

It has no validation-data path and creates no validation grants.

Run #1 searches the mature price/market feature vocabulary using:
- generic discovery
- cross-sectional
- conditional
- interaction
- regime
- time-series
- distribution
- residual
- anomaly

The output is discovery evidence only. Nothing here constitutes
out-of-sample validation.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from research_tools.cascade_reversal_study import (
    load_minute_bars,
)

from research_tools.module_factory.conditional_scientist import (
    discover as discover_conditional,
)
from research_tools.module_factory.cross_sectional_scientist import (
    discover as discover_cross_sectional,
)
from research_tools.module_factory.discovery_engine import (
    discover as discover_generic,
)
from research_tools.module_factory.bounded_feature_cache import prepare_bucketed_feature_partitions
from research_tools.module_factory.partitioned_discovery import (
    feature_inventory,
    run_supported_partitioned_discovery,
)
from research_tools.module_factory.distribution_scientist import (
    discover_distribution_states,
)
from research_tools.module_factory.feature_matrix import (
    build_feature_matrix,
)
from research_tools.module_factory.interaction_scientist import (
    discover_interactions,
)
from research_tools.module_factory.regime_scientist import (
    discover_regimes,
)
from research_tools.module_factory.residual_scientist import (
    discover_residual_relationships,
)
from research_tools.module_factory.research_row_adapter import (
    from_feature_row,
)
from research_tools.module_factory.time_series_scientist import (
    discover_lag_structures,
)
from research_tools.module_factory.anomaly_scientist import (
    discover_anomaly_states,
)
from research_tools.module_factory.real_datasets import (
    AUG28_DATASET_ID,
    build_real_dataset_controller,
)
from research_tools.module_factory.idea_library import IdeaLibrary
from research_tools.module_factory.idea_translator import translate_library
from research_tools.module_factory.research_scientist import profile_dataset


HORIZONS = (1, 5, 10, 20)

# Bounded first-pass search.
MAX_BASE_FEATURES = 10
MAX_STATE_FEATURES = 5
MAX_RESULTS_PER_SCIENTIST = 20


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            key: _jsonable(item)
            for key, item
            in asdict(value).items()
        }

    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item
            in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _jsonable(item)
            for item in value
        ]

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None

    return value


def _score(item: Any) -> float:
    value = getattr(
        item,
        "score",
        float("-inf"),
    )

    try:
        value = float(value)
    except (TypeError, ValueError):
        return float("-inf")

    if not math.isfinite(value):
        return float("-inf")

    return value


def _top(
    values: list[Any],
    n: int = 10,
) -> list[Any]:
    return sorted(
        values,
        key=_score,
        reverse=True,
    )[:n]


def _feature_quality(
    rows,
    name: str,
) -> tuple[int, float]:
    values = [
        row.features.get(
            name,
            float("nan"),
        )
        for row in rows
    ]

    finite = [
        float(value)
        for value in values
        if _finite(value)
    ]

    if not finite:
        return (0, 0.0)

    mean = sum(finite) / len(finite)

    variance = sum(
        (value - mean) ** 2
        for value in finite
    ) / len(finite)

    return (
        len(finite),
        math.sqrt(variance),
    )


def _select_features(
    rows,
) -> list[str]:
    names = sorted(
        {
            name
            for row in rows
            for name in row.features
        }
    )

    ranked = []

    for name in names:
        count, std = (
            _feature_quality(
                rows,
                name,
            )
        )

        if (
            count >= 100
            and std > 1e-12
        ):
            ranked.append(
                (
                    count,
                    std,
                    name,
                )
            )

    ranked.sort(
        reverse=True
    )

    return [
        name
        for _, _, name
        in ranked[
            :MAX_BASE_FEATURES
        ]
    ]


def _run_stage(
    name,
    function,
):
    started = time.perf_counter()

    print(
        f"STAGE_START {name}",
        flush=True,
    )

    result = function()

    elapsed = (
        time.perf_counter()
        - started
    )

    print(
        f"STAGE_DONE {name} "
        f"seconds={elapsed:.3f} "
        f"results={len(result)}",
        flush=True,
    )

    return result, elapsed


def _summary(
    label: str,
    discoveries: list[Any],
) -> None:
    print()
    print(
        f"=== {label} "
        f"({len(discoveries)}) ==="
    )

    for rank, item in enumerate(
        _top(
            discoveries,
            10,
        ),
        start=1,
    ):
        print(
            rank,
            json.dumps(
                _jsonable(item),
                sort_keys=True,
            ),
        )


def run(
    repo_root: str | Path,
    output_path: str | Path,
    idea_library_path: str | Path | None = None,
    discovery_sources: list[str | Path] | None = None,
    discovery_dataset_ids: list[str] | None = None,
    feature_stride: int = 1,
    feature_cache_root: str | Path | None = None,
    feature_cache_max_mb: int = 512,
    before_feature_chunk: Any = None,
) -> dict[str, Any]:
    if feature_stride < 1:
        raise ValueError("feature_stride must be >= 1")
    root = Path(
        repo_root
    ).resolve()

    if discovery_sources is None:
        controller = build_real_dataset_controller(root)
        discovery_access = controller.discovery_access(AUG28_DATASET_ID)
        sources = [Path(discovery_access.resource_id)]
        dataset_ids = [discovery_access.dataset_id]
    else:
        sources = [Path(item) for item in discovery_sources]
        dataset_ids = list(discovery_dataset_ids or ())
        if len(dataset_ids) != len(sources):
            raise ValueError("each rolling discovery source requires a dataset id")

    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)

    started = time.perf_counter()

    print(
        "AUTHORIZED_DISCOVERY_DATASET",
        ",".join(dataset_ids),
        flush=True,
    )

    print(
        "READING_DISCOVERY_RESOURCE",
        ",".join(str(item) for item in sources),
        flush=True,
    )

    if feature_cache_root is not None:
        partitions = prepare_bucketed_feature_partitions(
            sources=sources,
            dataset_ids=dataset_ids,
            cache_root=feature_cache_root,
            horizons=HORIZONS,
            max_lookback=60,
            stride=feature_stride,
            max_cache_mb=feature_cache_max_mb,
            bucket_count=32,
            before_chunk=before_feature_chunk,
            progress=lambda event: print(
                "FACTORY_RESEARCH_CHECKPOINT " + json.dumps(event, sort_keys=True),
                flush=True,
            ),
        )
        inventory = feature_inventory(partitions)
        selected_features = inventory["selected_features"]
        families = run_supported_partitioned_discovery(
            paths=partitions,
            selected_features=selected_features,
            checkpoint_root=Path(feature_cache_root) / "questions",
            horizons=HORIZONS,
            before_question=before_feature_chunk,
            progress=lambda event: print(
                "FACTORY_RESEARCH_QUESTION " + json.dumps(event, sort_keys=True),
                flush=True,
            ),
        )
        elapsed = time.perf_counter() - started
        report = {
            "run_id": "factory-real-discovery-partitioned-v1",
            "dataset_id": dataset_ids[0] if len(dataset_ids) == 1 else None,
            "discovery_dataset_ids": dataset_ids,
            "validation_data_accessed": False,
            "symbols": inventory["symbols"],
            "feature_rows": inventory["rows"],
            "feature_stride": feature_stride,
            "full_resolution": feature_stride == 1,
            "bounded_feature_cache": True,
            "selected_features": selected_features,
            "literature_guided": False,
            "literature_question_count": 0,
            "literature_idea_ids": [],
            "horizons": list(HORIZONS),
            "elapsed_seconds": elapsed,
            "families": {
                "generic": [], "cross_sectional": [], "conditional": [],
                "interaction": [], "regime": [_jsonable(x) for x in families["regime"]],
                "time_series": [], "distribution": [_jsonable(x) for x in families["distribution"]],
                "residual": [], "anomaly": [],
            },
            "audit": [],
        }
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("REPORT", destination, flush=True)
        return report

    bars_by_symbol = load_minute_bars([str(item) for item in sources])
    print("SYMBOLS", len(bars_by_symbol), flush=True)
    rows = build_feature_matrix(
        bars_by_symbol, horizons=HORIZONS, max_lookback=60,
        stride=feature_stride,
    )

    print(
        "FEATURE_ROWS",
        len(rows),
        flush=True,
    )

    if not rows:
        raise RuntimeError(
            "feature matrix is empty"
        )

    selected_features = (
        _select_features(
            rows
        )
    )

    literature_questions = []
    if idea_library_path is not None and Path(idea_library_path).exists():
        ideas = IdeaLibrary(idea_library_path).current()
        literature_questions = translate_library(
            ideas, profile_dataset(rows), horizons=HORIZONS,
            max_questions_per_idea=20,
        )
        guided = []
        for translated in sorted(
            literature_questions,
            key=lambda item: item.question.priority,
            reverse=True,
        ):
            guided.extend(translated.question.features)
        selected_features = list(dict.fromkeys(
            [feature for feature in guided if feature in selected_features]
            + selected_features
        ))[:MAX_BASE_FEATURES]

    print(
        "SELECTED_FEATURES",
        len(selected_features),
    )

    print(
        "FEATURE_NAMES",
        ",".join(
            selected_features
        ),
    )

    unified_rows = [
        from_feature_row(row)
        for row in rows
    ]

    # Generic engine expects rows grouped by day.
    rows_by_day = {}
    for row in rows:
        rows_by_day.setdefault(row.minute.date().isoformat(), []).append(row)

    generic, generic_seconds = _run_stage(
        "generic",
        lambda: discover_generic(
            rows_by_day
        ),
    )

    cross_sectional, cross_sectional_seconds = _run_stage(
        "cross_sectional",
        lambda: discover_cross_sectional(
            rows,
            features=selected_features,
            horizons=HORIZONS,
        ),
    )

    state_features = (
        selected_features[
            :MAX_STATE_FEATURES
        ]
    )

    conditional, conditional_seconds = _run_stage(
        "conditional",
        lambda: discover_conditional(
            rows,
            signal_features=selected_features,
            state_features=state_features,
            horizons=HORIZONS,
        ),
    )

    interaction, interaction_seconds = _run_stage(
        "interaction",
        lambda: discover_interactions(
            unified_rows,
            feature_names=selected_features,
            horizons=HORIZONS,
            max_features=MAX_BASE_FEATURES,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    regime, regime_seconds = _run_stage(
        "regime",
        lambda: discover_regimes(
            unified_rows,
            feature_names=selected_features,
            regime_feature_names=state_features,
            horizons=HORIZONS,
            max_features=MAX_BASE_FEATURES,
            max_regime_features=MAX_STATE_FEATURES,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    time_series, time_series_seconds = _run_stage(
        "time_series",
        lambda: discover_lag_structures(
            unified_rows,
            feature_names=selected_features,
            horizons=HORIZONS,
            max_features=MAX_BASE_FEATURES,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    distribution, distribution_seconds = _run_stage(
        "distribution",
        lambda: discover_distribution_states(
            unified_rows,
            feature_names=selected_features,
            horizons=HORIZONS,
            max_features=MAX_BASE_FEATURES,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    residual, residual_seconds = _run_stage(
        "residual",
        lambda: discover_residual_relationships(
            unified_rows,
            candidate_names=selected_features,
            control_names=state_features,
            horizons=HORIZONS,
            max_candidates=MAX_BASE_FEATURES,
            max_controls=5,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    # Diverse 2-feature anomaly groups.
    anomaly_groups = []

    for i, left in enumerate(
        selected_features[:12]
    ):
        for right in (
            selected_features[
                i + 1:12
            ]
        ):
            anomaly_groups.append(
                (
                    left,
                    right,
                )
            )

    anomaly, anomaly_seconds = _run_stage(
        "anomaly",
        lambda: discover_anomaly_states(
            unified_rows,
            feature_groups=anomaly_groups,
            horizons=HORIZONS,
            max_groups=20,
            max_features_per_group=2,
            max_results=MAX_RESULTS_PER_SCIENTIST,
        ),
    )

    families = {
        "generic":
            generic,
        "cross_sectional":
            cross_sectional,
        "conditional":
            conditional,
        "interaction":
            interaction,
        "regime":
            regime,
        "time_series":
            time_series,
        "distribution":
            distribution,
        "residual":
            residual,
        "anomaly":
            anomaly,
    }

    elapsed = (
        time.perf_counter()
        - started
    )

    report = {
        "run_id":
            "factory-real-discovery-001",
        "dataset_id": dataset_ids[0] if len(dataset_ids) == 1 else None,
        "discovery_dataset_ids": dataset_ids,
        "validation_data_accessed":
            False,
        "symbols":
            len(
                {row.symbol for row in rows}
            ),
        "feature_rows":
            len(rows),
        "feature_stride": feature_stride,
        "bounded_feature_cache": feature_cache_root is not None,
        "selected_features":
            selected_features,
        "literature_guided": bool(literature_questions),
        "literature_question_count": len(literature_questions),
        "literature_idea_ids": sorted({
            item.idea_id for item in literature_questions
        }),
        "horizons":
            list(HORIZONS),
        "elapsed_seconds":
            elapsed,
        "families": {
            name: [
                _jsonable(item)
                for item
                in values
            ]
            for name, values
            in families.items()
        },
        "audit": [
            _jsonable(event)
            for event
            in (controller.audit_log() if discovery_sources is None else ())
        ],
    }

    destination = Path(
        output_path
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print()
    print(
        "ELAPSED_SECONDS",
        round(
            elapsed,
            3,
        ),
    )

    for label, values in families.items():
        _summary(
            label.upper(),
            values,
        )

    print()
    print(
        "REPORT",
        destination,
    )

    print(
        "VALIDATION_DATA_ACCESSED",
        False,
    )

    print(
        "SEP_2_OPENED",
        False,
    )

    return report

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    output_path = (
        repo_root
        / "research_data"
        / "factory_real_discovery_001.json"
    )

    run(
        repo_root=repo_root,
        output_path=output_path,
    )
