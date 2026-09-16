"""After-hours rolling discovery -> sealed validation -> shadow admission."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import resource
from pathlib import Path
import time

from research_tools.module_factory.dataset_lifecycle import DatasetLifecycleController, RegisteredDataset
from research_tools.module_factory.frozen_validation_dispatch import validate_frozen_specification
from research_tools.module_factory.generated_strategy import GeneratedStrategySpec
from research_tools.module_factory.causal_compiler import compile_frozen_hypothesis
from research_tools.module_factory.hypothesis_protocol import DatasetRole, freeze_hypothesis, make_specification
from research_tools.module_factory.population_manager import FactoryPopulationManager
from research_tools.module_factory.resource_governor import ResourceGovernor
from research_tools.module_factory.literature_scientist import after_market_hours, run_once as run_literature
from research_tools.module_factory.real_discovery_run import run as run_discovery
from research_tools.module_factory.rolling_datasets import RollingDatasetLedger, compact_rich_archive, discover_completed_archives
from research_tools.module_factory.validation_execution import execute_sealed_batch
from research_tools.module_factory.bounded_feature_cache import (
    FeaturePreparationDeferred,
    prepare_bucketed_feature_partitions,
)


SUPPORTED = ("regime", "distribution")

DEFAULT_NORMAL_INTERVAL_SECONDS = 21600.0
DEFAULT_RESOURCE_RETRY_SECONDS = 900.0
DEFAULT_MEMORY_RETRY_SECONDS = 1800.0
DEFAULT_MARKET_HOURS_RETRY_SECONDS = 3600.0
DEFAULT_ERROR_RETRY_SECONDS = 900.0
MAX_ERROR_RETRY_SECONDS = 3600.0


def _atomic_status(root: Path, payload: dict) -> None:
    """Persist research progress/errors even when stdout logs roll away."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "research_status.json"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _next_delay_seconds(
    result: dict,
    *,
    normal_interval_seconds: float = DEFAULT_NORMAL_INTERVAL_SECONDS,
    consecutive_errors: int = 0,
) -> float:
    """Choose a cheap retry delay without busy-looping expensive research.

    Completed/no-new-data runs retain the normal six-hour cadence. Durable
    checkpoint and resource deferrals retry soon enough to use recovered
    capacity during the same after-hours window. Unexpected errors use bounded
    exponential backoff.
    """
    status = str(result.get("status", "ERROR"))
    normal = max(3600.0, float(normal_interval_seconds))

    if status == "DEFERRED_RESOURCES":
        return DEFAULT_RESOURCE_RETRY_SECONDS
    if status == "DEFERRED_MEMORY_LIMIT":
        return DEFAULT_MEMORY_RETRY_SECONDS
    if status == "DEFERRED_MARKET_HOURS":
        return DEFAULT_MARKET_HOURS_RETRY_SECONDS
    if status == "ERROR":
        exponent = max(0, int(consecutive_errors) - 1)
        return min(
            MAX_ERROR_RETRY_SECONDS,
            DEFAULT_ERROR_RETRY_SECONDS * (2 ** exponent),
        )
    return normal


def _resource_decision(data_root: Path):
    return ResourceGovernor(
        min_memory_available_mb=float(os.getenv("FACTORY_MIN_MEMORY_AVAILABLE_MB", "1024")),
        min_data_free_mb=float(os.getenv("FACTORY_MIN_DATA_FREE_MB", "1024")),
        max_load_per_cpu=float(os.getenv("FACTORY_MAX_LOAD_PER_CPU", "1.25")),
    ).check(data_root=data_root)


def _research_stride() -> int:
    # Rolling production research is full resolution. Memory is bounded by
    # durable day partitions and question-at-a-time evaluation, not sampling.
    return 1


def _apply_process_memory_limit() -> int:
    """Enforce a per-process ceiling independent of shared-host snapshots."""
    limit_mb = max(512, int(os.getenv("FACTORY_RESEARCH_MAX_ADDRESS_MB", "1536")))
    limit = limit_mb * 1024 * 1024
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    effective = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (effective, hard))
    return int(effective / 1024 / 1024)


def _candidate_specs(report: dict, *, limit: int = 60):
    candidates = []
    provenance = tuple("idea:" + item for item in report.get("literature_idea_ids", []))
    dataset_ids = tuple(report.get("discovery_dataset_ids", []))
    for scientist in SUPPORTED:
        ranked = sorted(report.get("families", {}).get(scientist, []), key=lambda row: float(row.get("score", 0)), reverse=True)
        for index, row in enumerate(ranked[: max(1, limit // len(SUPPORTED))]):
            if scientist == "regime":
                features = (row["feature"], row["regime_feature"])
                parameters = {key: row[key] for key in (
                    "low_threshold", "high_threshold", "direction_low", "direction_high", "sign_reversal"
                )}
            else:
                features = (row["feature"],)
                parameters = {key: row[key] for key in (
                    "low_threshold", "high_threshold", "direction_low", "direction_high", "move_threshold", "dominant_effect"
                )}
            specification = make_specification(
                scientist=scientist,
                discovery_id=f"rolling:{scientist}:{index}:{hashlib.sha1(json.dumps(row,sort_keys=True).encode()).hexdigest()[:12]}",
                target="forward_return", horizon=int(row["horizon"]), features=features,
                parameters=parameters, direction=row.get("direction"),
                ancestry=tuple(row.get("ancestry", ("PRICE",))),
                provenance=provenance or ("internal_discovery",),
                discovery_dataset_ids=dataset_ids,
                multiple_testing_family=f"rolling:{scientist}",
                tests_considered=max(1, len(report.get("families", {}).get(scientist, []))),
                min_samples=1000, min_events=100,
            )
            candidates.append((freeze_hypothesis(specification), float(row.get("score", 0))))
    return candidates[:limit]


def _generated_specs(frozen, result: dict):
    return list(compile_frozen_hypothesis(frozen))


def run_once(*, data_root: Path = Path("/data"), max_shadow_modules: int = 100, force: bool = False) -> dict:
    data_root = Path(data_root); root = data_root / "module_factory"
    if not force and not after_market_hours():
        return {"status": "DEFERRED_MARKET_HOURS"}
    decision = _resource_decision(data_root)
    if not decision.allowed:
        return {"status": "DEFERRED_RESOURCES", "reasons": decision.reasons}
    literature = run_literature(data_root=data_root, force=force)
    ledger = RollingDatasetLedger(root / "dataset_ledger.json")
    skipped_archives = []
    for day, source in discover_completed_archives(data_root / "research_market"):
        if ledger.is_late_unassigned(day):
            skipped_archives.append({
                "day": day,
                "source": str(source),
                "error": "late historical archive predates immutable ledger tail",
            })
            continue
        compact = root / "datasets" / f"quotes_{day.replace('-', '')}.csv.gz"
        compact_result = compact_rich_archive(source, compact)
        if not compact_result.get("usable", True):
            skipped_archives.append({
                "day": day,
                "source": str(source),
                "error": compact_result.get("error", "unusable archive"),
            })
            continue
        ledger.assign(day, source_path=source, compact_path=compact)
    discovery = ledger.datasets("DISCOVERY")
    validations = ledger.datasets("VALIDATION")
    if len(discovery) < 4 or not validations:
        return {"status": "WAITING_FOR_DATA", "discovery_days": len(discovery), "validation_days": len(validations), "skipped_archives": skipped_archives, "literature": literature}

    lifecycle = DatasetLifecycleController(state_path=root / "rolling_validation_state.json")
    for item in ledger.datasets():
        lifecycle.register(RegisteredDataset(
            dataset_id=item.dataset_id, resource_id=item.compact_path,
            role=DatasetRole(item.role), sealed=item.sealed,
        ))
    validation = next((item for item in validations if not lifecycle.validation_dataset_spent(item.dataset_id)), None)
    if validation is None:
        return {"status": "WAITING_FOR_UNUSED_VALIDATION", "skipped_archives": skipped_archives}

    discovery_report_path = root / "reports" / f"discovery_for_{validation.day}.json"
    try:
        _atomic_status(root, {
            "status": "DISCOVERY_RUNNING",
            "validation_day": validation.day,
            "updated_at": time.time(),
        })
        def discovery_progress(event):
            _atomic_status(root, {
                "status": "DISCOVERY_RUNNING",
                "validation_day": validation.day,
                "stage": "questions",
                **event,
                "updated_at": time.time(),
            })

        report = run_discovery(
            repo_root=Path.cwd(), output_path=discovery_report_path,
            idea_library_path=root / "idea_library.jsonl",
            discovery_sources=[item.compact_path for item in discovery if item.day < validation.day],
            discovery_dataset_ids=[item.dataset_id for item in discovery if item.day < validation.day],
            feature_stride=_research_stride(),
            feature_cache_root=root / "feature_cache" / f"discovery_for_{validation.day}",
            feature_cache_max_mb=int(os.getenv("FACTORY_RESEARCH_CACHE_MAX_MB", "512")),
            before_feature_chunk=lambda: _resource_decision(data_root).reasons,
            progress=discovery_progress,
        )
    except FeaturePreparationDeferred as exc:
        return {
            "status": "DEFERRED_RESOURCES",
            "reasons": tuple(filter(None, str(exc).split(","))),
            "checkpointed": True,
        }
    scored = _candidate_specs(report)
    frozen = tuple(item[0] for item in scored)
    if not frozen:
        return {"status": "NO_TRANSLATABLE_CANDIDATES"}
    # Discovery rows/bars are intentionally not retained into sealed
    # validation. Reclaim them before opening the validation dataset.
    gc.collect()
    decision = _resource_decision(data_root)
    if not decision.allowed:
        return {
            "status": "DEFERRED_RESOURCES",
            "reasons": decision.reasons,
            "discovery_complete": True,
        }
    batch = lifecycle.create_validation_batch(validation.dataset_id, frozen)

    def load_rows(resource_id):
        paths = prepare_bucketed_feature_partitions(
            sources=[resource_id], dataset_ids=[validation.dataset_id],
            cache_root=root / "feature_cache" / f"validation_{validation.day}",
            horizons=(1, 5, 10, 20), max_lookback=60, stride=1,
            max_cache_mb=int(os.getenv("FACTORY_RESEARCH_CACHE_MAX_MB", "512")),
            before_chunk=lambda: _resource_decision(data_root).reasons,
        )
        from research_tools.module_factory.bounded_feature_cache import iter_partition_rows
        return list(iter_partition_rows(paths))

    validation_report, _ = execute_sealed_batch(
        controller=lifecycle, batch=batch, frozen=frozen,
        load_rows=load_rows, validate=validate_frozen_specification,
        report_path=root / "reports" / f"validation_{validation.day}.json",
    )
    scores = {item[0].hypothesis_id: item[1] for item in scored}
    manager = FactoryPopulationManager(
        registry_path=root / "module_registry.json",
        spec_path=root / "generated_strategies.json",
        max_shadow_modules=max_shadow_modules,
    )
    registered = []
    for frozen_item, result_row in zip(frozen, validation_report["results"]):
        result = result_row["result"]
        effect = float(result.get("primary_effect", float("nan")))
        if (
            not result.get("expected_positive")
            or not math.isfinite(effect)
            or effect <= 0
            or int(result.get("n_samples", 0)) < frozen_item.specification.min_samples
            or int(result.get("n_events", 0)) < frozen_item.specification.min_events
            or int(result.get("independent_time_units", 0)) < 5
        ):
            continue
        for generated in _generated_specs(frozen_item, result):
            manager.register_historical_pass(spec=generated, score=scores[frozen_item.hypothesis_id])
            registered.append(generated.module_id)
    admitted = manager.admit_best(registered)
    return {
        "status": "OK", "validation_day": validation.day,
        "tested": len(frozen), "registered": registered,
        "admitted": [item.module_id for item in admitted],
        "literature_guided": report.get("literature_guided", False),
        "literature": literature,
        "skipped_archives": skipped_archives,
    }


def main() -> None:
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    memory_limit_mb = _apply_process_memory_limit()
    print(
        "FACTORY_RESEARCH_LIMITS "
        + json.dumps({
            "max_address_mb": memory_limit_mb,
            "feature_stride": _research_stride(),
        }, sort_keys=True),
        flush=True,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/data")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_NORMAL_INTERVAL_SECONDS,
    )
    args = parser.parse_args()
    consecutive_errors = 0
    while True:
        try:
            result = run_once(
                data_root=Path(args.data_root),
                max_shadow_modules=int(os.getenv("FACTORY_MAX_SHADOW_MODULES", "100")),
                force=args.force,
            )
        except MemoryError:
            result = {
                "status": "DEFERRED_MEMORY_LIMIT",
                "max_address_mb": memory_limit_mb,
            }
        except Exception as exc:
            result = {"status": "ERROR", "error": type(exc).__name__ + ": " + str(exc)}
        result = {**result, "updated_at": time.time()}
        try:
            _atomic_status(Path(args.data_root) / "module_factory", result)
        except OSError:
            pass
        print("FACTORY_RESEARCH " + json.dumps(result, sort_keys=True), flush=True)
        if not args.loop:
            break
        if result.get("status") == "ERROR":
            consecutive_errors += 1
        else:
            consecutive_errors = 0
        delay_seconds = _next_delay_seconds(
            result,
            normal_interval_seconds=args.interval_seconds,
            consecutive_errors=consecutive_errors,
        )
        print(
            "FACTORY_RESEARCH_NEXT "
            + json.dumps({
                "delay_seconds": delay_seconds,
                "status": result.get("status"),
            }, sort_keys=True),
            flush=True,
        )
        time.sleep(delay_seconds)


if __name__ == "__main__":
    main()
