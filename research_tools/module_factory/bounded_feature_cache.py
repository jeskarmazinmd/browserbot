"""Bounded, resumable preparation of historical Factory feature rows.

Raw minute bars are opened one archive at a time.  The resulting feature rows
are atomically checkpointed before the raw bars are released, so a worker
restart never has to repeat completed archives and multiple raw archives are
never resident together.
"""

from __future__ import annotations

import gc
import gzip
import hashlib
import csv
import json
import math
import os
import pickle
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable


class FeatureCacheLimitError(RuntimeError):
    """The bounded research cache would exceed its configured disk budget."""


class FeaturePreparationDeferred(RuntimeError):
    """Resource pressure requested a safe pause between archive chunks."""


def _fingerprint(source: Path, *, dataset_id: str, horizons: tuple[int, ...],
                 max_lookback: int, stride: int) -> str:
    stat = source.stat()
    payload = {
        "dataset_id": dataset_id,
        "source": str(source.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "horizons": horizons,
        "max_lookback": max_lookback,
        "stride": stride,
        "format": 1,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _atomic_pickle(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", compresslevel=1) as compressed:
            pickle.dump(payload, compressed, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_pickle(path: Path) -> dict:
    with gzip.open(path, "rb") as handle:
        return pickle.load(handle)


def prepare_feature_rows(
    *,
    sources: Iterable[str | Path],
    dataset_ids: Iterable[str],
    cache_root: str | Path,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
    max_lookback: int = 60,
    stride: int = 10,
    max_cache_mb: int = 512,
    bar_loader: Callable | None = None,
    matrix_builder: Callable | None = None,
    progress: Callable[[dict], None] | None = None,
    before_chunk: Callable[[], tuple[str, ...]] | None = None,
    _return_partitions: bool = False,
) -> list[Any]:
    """Return combined rows while never retaining two raw archives at once."""
    source_paths = tuple(Path(item) for item in sources)
    ids = tuple(dataset_ids)
    if len(source_paths) != len(ids):
        raise ValueError("each feature source requires a dataset id")
    if stride < 1:
        raise ValueError("stride must be >= 1")
    if bar_loader is None:
        from research_tools.cascade_reversal_study import load_minute_bars
        bar_loader = load_minute_bars
    if matrix_builder is None:
        from research_tools.module_factory.feature_matrix import build_feature_matrix
        matrix_builder = build_feature_matrix

    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    fingerprints = tuple(
        _fingerprint(
            source, dataset_id=dataset_id, horizons=horizons,
            max_lookback=max_lookback, stride=stride,
        )
        for source, dataset_id in zip(source_paths, ids)
    )
    expected_names = {f"{item}.pickle.gz" for item in fingerprints}
    for stale in cache_root.glob("*.pickle.gz"):
        if stale.name not in expected_names:
            stale.unlink(missing_ok=True)
    for stale in cache_root.glob("*.pickle.gz.tmp"):
        stale.unlink(missing_ok=True)
    cache_paths: list[Path] = []

    for index, (source, dataset_id, fingerprint) in enumerate(
        zip(source_paths, ids, fingerprints), start=1
    ):
        cache_path = cache_root / f"{fingerprint}.pickle.gz"
        cache_paths.append(cache_path)
        reused = False
        if cache_path.exists():
            try:
                cached = _read_pickle(cache_path)
                reused = cached.get("fingerprint") == fingerprint
            except (EOFError, OSError, pickle.PickleError, AttributeError, ValueError):
                reused = False
            if not reused:
                cache_path.unlink(missing_ok=True)

        if not reused:
            reasons = tuple(before_chunk() if before_chunk is not None else ())
            if reasons:
                raise FeaturePreparationDeferred(",".join(reasons))
            bars = bar_loader([str(source)])
            try:
                rows = matrix_builder(
                    bars, horizons=horizons, max_lookback=max_lookback,
                    stride=stride,
                )
                _atomic_pickle(cache_path, {
                    "version": 1, "fingerprint": fingerprint, "rows": rows,
                })
            finally:
                del bars
                gc.collect()
            del rows
            gc.collect()

        cache_bytes = sum(path.stat().st_size for path in cache_paths if path.exists())
        if cache_bytes > max(1, max_cache_mb) * 1024 * 1024:
            cache_path.unlink(missing_ok=True)
            raise FeatureCacheLimitError(
                f"feature cache {cache_bytes / 1024 / 1024:.1f} MB exceeds "
                f"{max_cache_mb} MB budget"
            )
        if progress is not None:
            progress({
                "archive": index, "archives": len(source_paths),
                "dataset_id": dataset_id, "reused": reused,
                "cache_mb": round(cache_bytes / 1024 / 1024, 2),
            })

    if _return_partitions:
        return cache_paths

    combined: list[Any] = []
    for cache_path in cache_paths:
        combined.extend(_read_pickle(cache_path)["rows"])
    return combined


def prepare_feature_partitions(**kwargs) -> tuple[Path, ...]:
    """Prepare/reuse partitions without combining their rows in memory."""
    return tuple(prepare_feature_rows(_return_partitions=True, **kwargs))


def iter_partition_rows(paths: Iterable[str | Path]):
    for path in paths:
        payload = _read_pickle(Path(path))
        yield from payload["rows"]
        del payload
        gc.collect()


def _bucket_index(symbol: str, bucket_count: int) -> int:
    return int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big") % bucket_count


def _prepare_raw_buckets(source: Path, root: Path, bucket_count: int) -> tuple[Path, ...]:
    """Stream a compact archive into deterministic buckets without loading it."""
    manifest = root / "COMPLETE"
    paths = tuple(root / f"bucket_{index:03d}.csv.gz" for index in range(bucket_count))
    if manifest.exists() and all(path.exists() for path in paths):
        return paths
    temporary = root.with_name(root.name + ".tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True, exist_ok=True)
    raw_handles = [gzip.open(temporary / path.name, "wt", newline="", compresslevel=1) for path in paths]
    try:
        with gzip.open(source, "rt", newline="") as incoming:
            reader = csv.DictReader(incoming)
            if not reader.fieldnames:
                raise ValueError(f"missing header in {source}")
            writers = [csv.DictWriter(handle, fieldnames=reader.fieldnames) for handle in raw_handles]
            for writer in writers:
                writer.writeheader()
            for row in reader:
                symbol = str(row.get("symbol", "")).strip().upper()
                if not symbol:
                    continue
                if symbol == "SPY":
                    for writer in writers:
                        writer.writerow(row)
                else:
                    writers[_bucket_index(symbol, bucket_count)].writerow(row)
    finally:
        for handle in raw_handles:
            handle.close()
    (temporary / "COMPLETE").write_text("1\n")
    if root.exists():
        shutil.rmtree(root)
    temporary.replace(root)
    return paths


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _inventory(rows) -> dict:
    stats: dict[str, list[float]] = {}
    symbols = set()
    for row in rows:
        symbols.add(row.symbol)
        for name, value in row.features.items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                continue
            item = stats.setdefault(name, [0, 0.0, 0.0])
            number = float(value)
            item[0] += 1
            item[1] += number
            item[2] += number * number
    return {"rows": len(rows), "symbols": sorted(symbols), "stats": stats}


def _select_from_inventories(inventories: Iterable[dict], limit: int = 10) -> list[str]:
    merged: dict[str, list[float]] = {}
    for inventory in inventories:
        for name, values in inventory["stats"].items():
            target = merged.setdefault(name, [0, 0.0, 0.0])
            target[0] += int(values[0])
            target[1] += float(values[1])
            target[2] += float(values[2])
    ranked = []
    for name, (count, total, total_square) in merged.items():
        if count < 100:
            continue
        variance = max(0.0, total_square / count - (total / count) ** 2)
        std = math.sqrt(variance)
        if std > 1e-12:
            ranked.append((int(count), std, name))
    ranked.sort(reverse=True)
    return [name for _, _, name in ranked[:limit]]


def _cache_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def prepare_bucketed_feature_partitions(
    *, sources: Iterable[str | Path], dataset_ids: Iterable[str],
    cache_root: str | Path, horizons: tuple[int, ...] = (1, 5, 10, 20),
    max_lookback: int = 60, stride: int = 1, bucket_count: int = 32,
    max_cache_mb: int = 512, bar_loader: Callable | None = None,
    matrix_builder: Callable | None = None, progress: Callable[[dict], None] | None = None,
    before_chunk: Callable[[], tuple[str, ...]] | None = None,
) -> tuple[Path, ...]:
    """Two-pass full-resolution build with only one symbol bucket resident."""
    if stride != 1:
        raise ValueError("bucketed rolling research requires stride=1")
    if bucket_count < 2:
        raise ValueError("bucket_count must be >= 2")
    if bar_loader is None:
        from research_tools.cascade_reversal_study import load_minute_bars
        bar_loader = load_minute_bars
    if matrix_builder is None:
        from research_tools.module_factory.feature_matrix import build_feature_matrix
        matrix_builder = build_feature_matrix
    source_paths, ids = tuple(map(Path, sources)), tuple(dataset_ids)
    if len(source_paths) != len(ids):
        raise ValueError("each feature source requires a dataset id")
    cache_root = Path(cache_root)
    # v2 stored every calculated feature and was too large for the production
    # volume. It is a reproducible cache, never evidence, and is superseded by
    # the selected-column v3 layout below.
    shutil.rmtree(cache_root / "symbol_buckets", ignore_errors=True)
    inventory_root = cache_root / "inventory_v3"
    raw_records = []
    inventories = []

    # Pass 1: every feature participates in global selection, but only compact
    # sufficient statistics survive each bucket.
    for source_number, (source, dataset_id) in enumerate(zip(source_paths, ids), start=1):
        source_key = _fingerprint(
            source, dataset_id=dataset_id, horizons=horizons,
            max_lookback=max_lookback, stride=1,
        )
        raw_root = cache_root / "raw_buckets" / source_key
        reasons = tuple(before_chunk() if before_chunk else ())
        if reasons:
            raise FeaturePreparationDeferred(",".join(reasons))
        raw_paths = _prepare_raw_buckets(source, raw_root, bucket_count)
        raw_records.append((source_number, dataset_id, source_key, raw_root, raw_paths))
        for bucket_number, raw_path in enumerate(raw_paths, start=1):
            inventory_path = inventory_root / f"{source_key}_{bucket_number - 1:03d}.json"
            reused = inventory_path.exists()
            if not reused:
                reasons = tuple(before_chunk() if before_chunk else ())
                if reasons:
                    raise FeaturePreparationDeferred(",".join(reasons))
                bars = bar_loader([str(raw_path)])
                try:
                    rows = matrix_builder(
                        bars, horizons=horizons, max_lookback=max_lookback, stride=1,
                    )
                    inventory = _inventory(rows)
                    inventory.update({
                        "version": 3, "source_fingerprint": source_key,
                        "bucket": bucket_number - 1,
                    })
                    _atomic_json(inventory_path, inventory)
                finally:
                    del bars
                    gc.collect()
                del rows
                gc.collect()
            inventory = json.loads(inventory_path.read_text())
            inventories.append(inventory)
            cache_bytes = _cache_bytes(cache_root)
            if cache_bytes > max(1, max_cache_mb) * 1024 * 1024:
                raise FeatureCacheLimitError(
                    f"feature cache {cache_bytes / 1024 / 1024:.1f} MB exceeds "
                    f"{max_cache_mb} MB budget"
                )
            if progress:
                progress({
                    "archive": source_number, "archives": len(source_paths),
                    "dataset_id": dataset_id, "bucket": bucket_number,
                    "buckets": bucket_count, "stage": "inventory", "reused": reused,
                    "cache_mb": round(cache_bytes / 1024 / 1024, 2),
                })

    selected = _select_from_inventories(inventories, limit=10)
    if not selected:
        raise RuntimeError("full-resolution feature inventory selected no features")
    selection_key = hashlib.sha256("|".join(selected).encode()).hexdigest()[:16]
    selected_parent = cache_root / "selected_symbol_buckets_v3"
    feature_root = selected_parent / selection_key
    for stale in selected_parent.iterdir() if selected_parent.exists() else ():
        if stale.is_dir() and stale.name != selection_key:
            shutil.rmtree(stale)
    feature_root.mkdir(parents=True, exist_ok=True)
    output: list[Path] = []

    # Pass 2: recalculate at stride 1, retain only the globally selected
    # columns and all forward outcomes, then release the bucket.
    for source_number, dataset_id, source_key, raw_root, raw_paths in raw_records:
        for bucket_number, raw_path in enumerate(raw_paths, start=1):
            destination = feature_root / f"{source_key}_{bucket_number - 1:03d}.pickle.gz"
            output.append(destination)
            reused = destination.exists()
            if not reused:
                reasons = tuple(before_chunk() if before_chunk else ())
                if reasons:
                    raise FeaturePreparationDeferred(",".join(reasons))
                bars = bar_loader([str(raw_path)])
                try:
                    rows = matrix_builder(
                        bars, horizons=horizons, max_lookback=max_lookback, stride=1,
                    )
                    for row in rows:
                        row.features = {
                            name: row.features.get(name, math.nan) for name in selected
                        }
                    _atomic_pickle(destination, {
                        "version": 3, "source_fingerprint": source_key,
                        "bucket": bucket_number - 1,
                        "selected_features": selected, "rows": rows,
                    })
                finally:
                    del bars
                    gc.collect()
                del rows
                gc.collect()
            cache_bytes = _cache_bytes(cache_root)
            if cache_bytes > max(1, max_cache_mb) * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise FeatureCacheLimitError(
                    f"feature cache {cache_bytes / 1024 / 1024:.1f} MB exceeds "
                    f"{max_cache_mb} MB budget"
                )
            if progress:
                progress({
                    "archive": source_number, "archives": len(source_paths),
                    "dataset_id": dataset_id, "bucket": bucket_number,
                    "buckets": bucket_count, "stage": "features", "reused": reused,
                    "selected_features": len(selected),
                    "cache_mb": round(cache_bytes / 1024 / 1024, 2),
                })
        shutil.rmtree(raw_root, ignore_errors=True)
    return tuple(output)
