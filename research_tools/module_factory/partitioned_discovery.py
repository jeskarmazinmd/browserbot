"""Full-resolution discovery over durable day partitions.

Partitions are rescanned for each bounded feature or feature-pair question.
This intentionally trades wall-clock time and disk reads for predictable
memory without dropping eligible minute observations.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import math
import os
from pathlib import Path
import pickle
from typing import Callable, Iterable

from research_tools.module_factory.bounded_feature_cache import (
    FeaturePreparationDeferred,
    iter_partition_rows,
)
from research_tools.module_factory.distribution_scientist import discover_distribution_states
from research_tools.module_factory.regime_scientist import discover_regimes
from research_tools.module_factory.unified_catalog import unified_catalog_by_name


@dataclass(slots=True)
class _ProjectedRow:
    symbol: str
    minute: object
    price: float
    names: tuple[str, ...]
    values: tuple[float, ...]
    horizons: tuple[int, ...]
    outcomes: tuple[float, ...]
    ancestries: tuple[tuple[str, ...], ...]

    def feature(self, name: str) -> float:
        try:
            return float(self.values[self.names.index(name)])
        except (ValueError, TypeError, IndexError):
            return math.nan

    def outcome(self, horizon: int) -> float:
        try:
            return float(self.outcomes[self.horizons.index(horizon)])
        except (ValueError, TypeError, IndexError):
            return math.nan

    def ancestry(self, name: str) -> tuple[str, ...]:
        try:
            return self.ancestries[self.names.index(name)]
        except (ValueError, IndexError):
            return ()


def _projected_rows(paths, names: tuple[str, ...], horizons: tuple[int, ...]):
    catalog = unified_catalog_by_name()
    ancestries = tuple(
        catalog[name].ancestry if name in catalog else ("DERIVED",)
        for name in names
    )
    for row in iter_partition_rows(paths):
        yield _ProjectedRow(
            symbol=row.symbol, minute=row.minute, price=float(row.price),
            names=names,
            values=tuple(row.features.get(name, math.nan) for name in names),
            horizons=horizons,
            outcomes=tuple(row.forward_returns.get(item, math.nan) for item in horizons),
            ancestries=ancestries,
        )


def feature_inventory(paths: Iterable[str | Path]) -> dict:
    stats: dict[str, list[float]] = {}
    symbols = set()
    rows = 0
    for row in iter_partition_rows(paths):
        rows += 1
        symbols.add(row.symbol)
        for name, value in row.features.items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                continue
            item = stats.setdefault(name, [0.0, 0.0, 0.0])
            number = float(value)
            item[0] += 1
            item[1] += number
            item[2] += number * number
    ranked = []
    for name, (count, total, total_square) in stats.items():
        if count < 100:
            continue
        variance = max(0.0, total_square / count - (total / count) ** 2)
        std = math.sqrt(variance)
        if std > 1e-12:
            ranked.append((int(count), std, name))
    ranked.sort(reverse=True)
    return {
        "rows": rows, "symbols": len(symbols),
        "selected_features": [name for _, _, name in ranked[:10]],
    }


def _checkpoint(path: Path, build: Callable[[], object]):
    if path.exists():
        try:
            with gzip.open(path, "rb") as handle:
                return pickle.load(handle), True
        except (OSError, EOFError, pickle.PickleError):
            path.unlink(missing_ok=True)
    result = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as handle:
            pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
        raw.flush()
        os.fsync(raw.fileno())
    temporary.replace(path)
    return result, False


def run_supported_partitioned_discovery(
    *, paths: Iterable[str | Path], selected_features: Iterable[str],
    checkpoint_root: str | Path, horizons: tuple[int, ...] = (1, 5, 10, 20),
    before_question: Callable[[], tuple[str, ...]] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict[str, list]:
    paths = tuple(Path(item) for item in paths)
    features = tuple(dict.fromkeys(selected_features))[:10]
    state_features = features[:5]
    scope_payload = "|".join(
        f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
        for path in paths
    ) + "|partitioned-scientists-v1"
    scope = hashlib.sha256(scope_payload.encode()).hexdigest()[:16]
    root = Path(checkpoint_root) / scope

    def check():
        reasons = tuple(before_question() if before_question is not None else ())
        if reasons:
            raise FeaturePreparationDeferred(",".join(reasons))

    distributions = []
    for feature in features:
        key = hashlib.sha256(("distribution|" + feature).encode()).hexdigest()
        check()
        result, reused = _checkpoint(
            root / f"{key}.pickle.gz",
            lambda feature=feature: discover_distribution_states(
                _projected_rows(paths, (feature,), horizons),
                feature_names=(feature,), horizons=horizons, max_features=1,
                max_results=50,
            ),
        )
        distributions.extend(result)
        if progress:
            progress({"scientist": "distribution", "feature": feature, "reused": reused})

    regimes = []
    for feature in features:
        for state in state_features:
            if feature == state:
                continue
            key = hashlib.sha256((f"regime|{feature}|{state}").encode()).hexdigest()
            check()
            result, reused = _checkpoint(
                root / f"{key}.pickle.gz",
                lambda feature=feature, state=state: discover_regimes(
                    _projected_rows(paths, (feature, state), horizons),
                    feature_names=(feature,), regime_feature_names=(state,),
                    horizons=horizons, max_features=1, max_regime_features=1,
                    max_results=50,
                ),
            )
            regimes.extend(result)
            if progress:
                progress({
                    "scientist": "regime", "feature": feature,
                    "regime_feature": state, "reused": reused,
                })
    distributions.sort(key=lambda item: item.score, reverse=True)
    regimes.sort(key=lambda item: item.score, reverse=True)
    return {"distribution": distributions[:20], "regime": regimes[:20]}
