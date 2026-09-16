from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from research_tools.module_factory.bounded_feature_cache import prepare_feature_partitions
from research_tools.module_factory.partitioned_discovery import run_supported_partitioned_discovery
from research_tools.module_factory.research_rows import UnifiedResearchRow
from research_tools.module_factory.distribution_scientist import discover_distribution_states
from research_tools.module_factory.regime_scientist import discover_regimes
from research_tools.module_factory.research_row_adapter import from_feature_row


def test_partitioned_scientists_match_in_memory_results(tmp_path: Path):
    sources = [tmp_path / "day1", tmp_path / "day2"]
    for source in sources:
        source.write_text(source.name)
    base = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)

    def loader(paths):
        day = 0 if paths[0].endswith("day1") else 1
        return {"day": day}

    def builder(bars, **_):
        day = bars["day"]
        return [
            SimpleNamespace(
                symbol=f"S{i % 7}", minute=base + timedelta(days=day, minutes=i),
                price=100.0 + i,
                features={"alpha": float(i + day * 3), "state": float((i * 7) % 31)},
                forward_returns={1: ((i % 9) - 4) * 0.1, 5: ((i % 13) - 6) * 0.1,
                                 10: ((i % 17) - 8) * 0.1, 20: ((i % 23) - 11) * 0.1},
            )
            for i in range(140)
        ]

    partitions = prepare_feature_partitions(
        sources=sources, dataset_ids=["d1", "d2"], cache_root=tmp_path / "cache",
        stride=1, bar_loader=loader, matrix_builder=builder,
    )
    actual = run_supported_partitioned_discovery(
        paths=partitions, selected_features=["alpha", "state"],
        checkpoint_root=tmp_path / "questions",
    )

    original = builder({"day": 0}) + builder({"day": 1})
    unified = [from_feature_row(row) for row in original]
    expected_distribution = discover_distribution_states(
        unified, feature_names=("alpha", "state"), max_features=2, max_results=50,
    )
    expected_regime = discover_regimes(
        unified, feature_names=("alpha", "state"), regime_feature_names=("alpha", "state"),
        max_features=2, max_regime_features=2, max_results=50,
    )
    assert actual["distribution"] == expected_distribution[:20]
    assert actual["regime"] == expected_regime[:20]

    reused = []
    run_supported_partitioned_discovery(
        paths=partitions, selected_features=["alpha", "state"],
        checkpoint_root=tmp_path / "questions", progress=reused.append,
    )
    assert reused and all(item["reused"] for item in reused)
    assert len(reused) == 26
    assert [item["completed"] for item in reused] == list(range(1, 27))
    assert all(item["total"] == 26 for item in reused)
    assert reused[-1]["percent"] == 100.0
    assert reused[-1]["reused_completed"] == 26
    assert reused[-1]["computed_completed"] == 0
