from __future__ import annotations

from pathlib import Path
import random
import csv
import gzip
from types import SimpleNamespace

from research_tools.module_factory.bounded_feature_cache import (
    FeatureCacheLimitError,
    iter_partition_rows,
    prepare_bucketed_feature_partitions,
    prepare_feature_rows,
)


def test_prepares_one_archive_at_a_time_and_reuses_checkpoint(tmp_path: Path):
    sources = [tmp_path / "one.gz", tmp_path / "two.gz"]
    for source in sources:
        source.write_bytes(b"archive")
    active = 0
    peak = 0
    loads = []

    def loader(paths):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        loads.append(paths[0])
        return {"source": paths[0]}

    def builder(bars, **kwargs):
        nonlocal active
        active -= 1
        return [bars["source"]]

    kwargs = dict(
        sources=sources, dataset_ids=["one", "two"],
        cache_root=tmp_path / "cache", stride=20,
        bar_loader=loader, matrix_builder=builder,
    )
    assert prepare_feature_rows(**kwargs) == [str(sources[0]), str(sources[1])]
    assert peak == 1
    assert len(loads) == 2

    assert prepare_feature_rows(**kwargs) == [str(sources[0]), str(sources[1])]
    assert len(loads) == 2


def test_source_change_invalidates_only_its_checkpoint(tmp_path: Path):
    sources = [tmp_path / "one.gz", tmp_path / "two.gz"]
    for source in sources:
        source.write_bytes(b"archive")
    loads = []

    def loader(paths):
        loads.append(paths[0])
        return paths[0]

    def builder(bars, **kwargs):
        return [bars]

    kwargs = dict(
        sources=sources, dataset_ids=["one", "two"],
        cache_root=tmp_path / "cache", stride=40,
        bar_loader=loader, matrix_builder=builder,
    )
    prepare_feature_rows(**kwargs)
    sources[1].write_bytes(b"changed archive")
    prepare_feature_rows(**kwargs)
    assert loads == [str(sources[0]), str(sources[1]), str(sources[1])]


def test_cache_budget_is_enforced(tmp_path: Path):
    source = tmp_path / "one.gz"
    source.write_bytes(b"archive")
    try:
        prepare_feature_rows(
            sources=[source], dataset_ids=["one"], cache_root=tmp_path / "cache",
            max_cache_mb=1, bar_loader=lambda _: {},
            matrix_builder=lambda *_args, **_kwargs: [
                random.Random(7).randbytes(2 * 1024 * 1024)
            ],
        )
    except FeatureCacheLimitError:
        pass
    else:
        raise AssertionError("expected cache disk budget failure")


def test_resource_pause_keeps_prior_checkpoint(tmp_path: Path):
    sources = [tmp_path / "one.gz", tmp_path / "two.gz"]
    for source in sources:
        source.write_bytes(b"archive")
    checks = 0
    loads = []

    def resources():
        nonlocal checks
        checks += 1
        return () if checks == 1 else ("memory_available_below_floor",)

    def loader(paths):
        loads.append(paths[0])
        return paths[0]

    try:
        prepare_feature_rows(
            sources=sources, dataset_ids=["one", "two"],
            cache_root=tmp_path / "cache", bar_loader=loader,
            matrix_builder=lambda bars, **_: [bars], before_chunk=resources,
        )
    except Exception as exc:
        assert type(exc).__name__ == "FeaturePreparationDeferred"
    else:
        raise AssertionError("expected resource deferral")
    assert loads == [str(sources[0])]

    rows = prepare_feature_rows(
        sources=sources, dataset_ids=["one", "two"],
        cache_root=tmp_path / "cache", bar_loader=loader,
        matrix_builder=lambda bars, **_: [bars], before_chunk=lambda: (),
    )
    assert rows == [str(sources[0]), str(sources[1])]
    assert loads == [str(sources[0]), str(sources[1])]


def test_bucketed_builder_preserves_every_symbol_and_bounds_each_load(tmp_path: Path):
    source = tmp_path / "quotes.csv.gz"
    fields = ["market_minute_utc", "symbol", "last"]
    with gzip.open(source, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for minute in range(3):
            for symbol in ["SPY", "A", "B", "C", "D", "E", "F"]:
                writer.writerow({
                    "market_minute_utc": f"2026-01-02T14:{30 + minute}:00+00:00",
                    "symbol": symbol, "last": 100 + minute,
                })
    loads = []

    def loader(paths):
        with gzip.open(paths[0], "rt", newline="") as handle:
            symbols = {row["symbol"] for row in csv.DictReader(handle)}
        loads.append(symbols)
        return symbols

    def builder(symbols, **_):
        return [SimpleNamespace(
            symbol=symbol, minute=f"m{i}", price=1.0,
            features={"x": float(i)}, forward_returns={1: 0.1},
        ) for symbol in symbols if symbol != "SPY" for i in range(120)]

    kwargs = dict(
        sources=[source], dataset_ids=["d1"], cache_root=tmp_path / "cache",
        bucket_count=4, bar_loader=loader, matrix_builder=builder,
    )
    paths = prepare_bucketed_feature_partitions(**kwargs)
    assert len(paths) == 4
    assert {row.symbol for row in iter_partition_rows(paths)} == {"A", "B", "C", "D", "E", "F"}
    assert len(loads) == 8
    assert all("SPY" in symbols and len(symbols) <= 4 for symbols in loads)

    prepare_bucketed_feature_partitions(**kwargs)
    assert len(loads) == 8


def test_bucketed_output_matches_existing_full_loader(tmp_path: Path):
    pytest = __import__("pytest")
    cascade = pytest.importorskip("research_tools.cascade_reversal_study")
    from research_tools.module_factory.feature_matrix import build_feature_matrix
    from research_tools.module_factory.rolling_datasets import COMPACT_FIELDS
    source = tmp_path / "quotes.csv.gz"
    with gzip.open(source, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPACT_FIELDS)
        writer.writeheader()
        for minute in range(200):
            timestamp = f"2026-01-02T{14 + (30 + minute) // 60:02d}:{(30 + minute) % 60:02d}:00+00:00"
            for offset, symbol in enumerate(("SPY", "AAA", "BBB")):
                writer.writerow({
                    "market_minute_utc": timestamp, "symbol": symbol,
                    "last": 100 + offset + minute * 0.01,
                    "bid": "", "ask": "", "bid_size_raw": "",
                    "ask_size_raw": "", "quote_time_ms": "",
                })
    expected = build_feature_matrix(
        cascade.load_minute_bars([str(source)]), stride=1,
    )
    paths = prepare_bucketed_feature_partitions(
        sources=[source], dataset_ids=["d1"], cache_root=tmp_path / "cache",
        bucket_count=4, stride=1,
    )
    actual = list(iter_partition_rows(paths))

    expected_by_key = {(row.symbol, row.minute): row for row in expected}
    assert {(row.symbol, row.minute) for row in actual} == set(expected_by_key)
    selected = set(actual[0].features)
    assert 1 <= len(selected) <= 10
    assert all(set(row.features) == selected for row in actual)
    for row in actual:
        prior = expected_by_key[(row.symbol, row.minute)]
        assert row.price == prior.price
        assert row.forward_returns == prior.forward_returns
        assert row.features == {name: prior.features[name] for name in selected}
