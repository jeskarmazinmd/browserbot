"""
Dry-run triage of an existing Module Factory discovery report.

IMPORTANT:
- Reads only the already-produced discovery JSON.
- Does not open raw market data.
- Does not request validation access.
- Does not create or freeze hypotheses.
- Does not create a validation batch.

Purpose:
1. remove provable semantic redundancies;
2. collapse nearby variants into scientific families;
3. retain the best-scoring representative per family;
4. print a compact candidate inventory for inspection.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_tools.module_factory.hypothesis_fingerprint import (
    feature_family,
    feature_timescale_bucket,
    fingerprint_anomaly,
    fingerprint_conditional,
    fingerprint_distribution,
    fingerprint_regime,
    fingerprint_residual,
    fingerprint_time_series,
)
from research_tools.module_factory.semantic_canonicalization import (
    canonicalize_expression,
)


REPORT_PATH = Path(
    "research_data/factory_real_discovery_001.json"
)


def _feature_signature(name: str) -> tuple[str, str]:
    return (
        feature_family(name),
        feature_timescale_bucket(name),
    )


def _stable_key(kind: str, payload) -> str:
    encoded = json.dumps(
        [kind, payload],
        sort_keys=True,
        separators=(",", ":"),
    )
    return encoded


def _generic_key(item: dict) -> str:
    return _stable_key(
        "generic",
        {
            "feature": _feature_signature(
                item["feature"]
            ),
            "horizon": item["horizon"],
            "direction": (
                1
                if item["mean_spearman"] >= 0
                else -1
            ),
        },
    )


def _cross_sectional_key(item: dict) -> str:
    return _stable_key(
        "cross_sectional",
        {
            "feature": _feature_signature(
                item["feature"]
            ),
            "horizon": item["horizon"],
            "direction": item[
                "preferred_sign"
            ],
        },
    )


def _interaction_analysis(
    item: dict,
) -> tuple[str | None, str | None]:
    expression = canonicalize_expression(
        operation=item["operation"],
        left=item["left"],
        right=item["right"],
    )

    # Provably not a novel interaction:
    # return_N - spy_relative_return_N
    # reduces exactly to SPY market return.
    if expression.operation == "market_return":
        return (
            None,
            "exactly_reduces_to_"
            f"{expression.value}_market_return_"
            f"{expression.lookback}",
        )

    left_signature = _feature_signature(
        item["left"]
    )
    right_signature = _feature_signature(
        item["right"]
    )

    if item["operation"] == "multiply":
        operands = tuple(
            sorted(
                (
                    left_signature,
                    right_signature,
                )
            )
        )
    else:
        operands = (
            left_signature,
            right_signature,
        )

    key = _stable_key(
        "interaction",
        {
            "operation": item["operation"],
            "operands": operands,
            "horizon": item["horizon"],
            "direction": item["direction"],
            "semantic_key":
                expression.semantic_key,
        },
    )

    return key, None


def _family_key(
    scientist: str,
    item: dict,
) -> tuple[str | None, str | None]:
    if scientist == "generic":
        return _generic_key(item), None

    if scientist == "cross_sectional":
        return (
            _cross_sectional_key(item),
            None,
        )

    if scientist == "conditional":
        result = fingerprint_conditional(
            signal_feature=item[
                "signal_feature"
            ],
            state_feature=item[
                "state_feature"
            ],
            horizon=item["horizon"],
            state_direction=item[
                "state_direction"
            ],
            preferred_sign=item[
                "preferred_sign"
            ],
        )
        return result.family_key, None

    if scientist == "interaction":
        return _interaction_analysis(item)

    if scientist == "regime":
        result = fingerprint_regime(
            feature=item["feature"],
            regime_feature=item[
                "regime_feature"
            ],
            horizon=item["horizon"],
            dominant_regime=item[
                "dominant_regime"
            ],
            direction_low=item[
                "direction_low"
            ],
            direction_high=item[
                "direction_high"
            ],
            sign_reversal=item[
                "sign_reversal"
            ],
        )
        return result.family_key, None

    if scientist == "distribution":
        result = fingerprint_distribution(
            feature=item["feature"],
            horizon=item["horizon"],
            dominant_effect=item[
                "dominant_effect"
            ],
            direction_low=item[
                "direction_low"
            ],
            direction_high=item[
                "direction_high"
            ],
        )
        return result.family_key, None

    if scientist == "residual":
        result = fingerprint_residual(
            candidate=item["candidate"],
            controls=tuple(
                item["controls"]
            ),
            horizon=item["horizon"],
            direction=item["direction"],
        )
        return result.family_key, None

    if scientist == "time_series":
        result = fingerprint_time_series(
            feature=item["feature"],
            horizon=item["horizon"],
            best_lag=item["best_lag"],
            direction=item["direction"],
            sign_change=item[
                "sign_change"
            ],
        )
        return result.family_key, None

    if scientist == "anomaly":
        result = fingerprint_anomaly(
            features=tuple(
                item["features"]
            ),
            horizon=item["horizon"],
            dominant_effect=item[
                "dominant_effect"
            ],
            direction=item["direction"],
        )
        return result.family_key, None

    raise ValueError(
        f"unsupported scientist: {scientist}"
    )


def _describe(
    scientist: str,
    item: dict,
) -> str:
    if scientist == "generic":
        return (
            f"{item['feature']} "
            f"h{item['horizon']} "
            f"rho={item['mean_spearman']:.4f} "
            f"edge={item['mean_edge']:.4f}"
        )

    if scientist == "cross_sectional":
        return (
            f"{item['feature']} "
            f"h{item['horizon']} "
            f"rank={item['mean_rank_correlation']:.4f} "
            f"spread={item['mean_high_minus_low']:.4f} "
            f"minutes={item['minutes']}"
        )

    if scientist == "conditional":
        return (
            f"{item['signal_feature']} "
            f"when {item['state_feature']}="
            f"{item['state_direction']} "
            f"h{item['horizon']} "
            f"rho={item['conditional_correlation']:.4f} "
            f"improve={item['improvement']:.4f}"
        )

    if scientist == "interaction":
        return (
            f"{item['left']} "
            f"{item['operation']} "
            f"{item['right']} "
            f"h{item['horizon']} "
            f"corr={item['interaction_correlation']:.4f} "
            f"increment={item['incremental_edge']:.4f}"
        )

    if scientist == "regime":
        return (
            f"{item['feature']} by "
            f"{item['regime_feature']} "
            f"h{item['horizon']} "
            f"low={item['low_correlation']:.4f} "
            f"high={item['high_correlation']:.4f} "
            f"reversal={item['sign_reversal']}"
        )

    if scientist == "distribution":
        return (
            f"{item['feature']} "
            f"h{item['horizon']} "
            f"effect={item['dominant_effect']} "
            f"move_asym={item['move_asymmetry']:.4f} "
            f"mean_asym={item['mean_asymmetry']:.4f}"
        )

    if scientist == "residual":
        return (
            f"{item['candidate']} "
            f"| controls={','.join(item['controls'])} "
            f"h{item['horizon']} "
            f"raw={item['raw_correlation']:.4f} "
            f"resid={item['residual_correlation']:.4f} "
            f"clarity={item['incremental_clarity']:.4f}"
        )

    if scientist == "time_series":
        return (
            f"{item['feature']} "
            f"h{item['horizon']} "
            f"lag={item['best_lag']} "
            f"best={item['best_correlation']:.4f} "
            f"now={item['contemporaneous_correlation']:.4f} "
            f"sign_change={item['sign_change']}"
        )

    if scientist == "anomaly":
        return (
            f"{'+'.join(item['features'])} "
            f"h{item['horizon']} "
            f"effect={item['dominant_effect']} "
            f"large_move={item['large_move_effect']:.4f} "
            f"direction={item['direction']}"
        )

    return repr(item)


def main() -> None:
    report = json.loads(
        REPORT_PATH.read_text()
    )

    if report.get(
        "validation_data_accessed"
    ):
        raise RuntimeError(
            "Refusing triage: report says "
            "validation data was accessed"
        )

    families = report["families"]

    print(
        "REPORT",
        REPORT_PATH,
    )
    print(
        "DATASET",
        report["dataset_id"],
    )
    print(
        "VALIDATION_DATA_ACCESSED",
        report["validation_data_accessed"],
    )
    print()

    total_raw = sum(
        len(items)
        for items in families.values()
    )

    print(
        "TOTAL_RAW_DISCOVERIES",
        total_raw,
    )

    total_representatives = 0
    rejected = []

    all_representatives = {}

    for scientist in (
        "generic",
        "cross_sectional",
        "conditional",
        "interaction",
        "regime",
        "distribution",
        "residual",
        "time_series",
        "anomaly",
    ):
        items = families[scientist]

        grouped = {}

        for item in items:
            key, rejection = _family_key(
                scientist,
                item,
            )

            if rejection is not None:
                rejected.append(
                    (
                        scientist,
                        rejection,
                        item,
                    )
                )
                continue

            current = grouped.get(key)

            if (
                current is None
                or float(item["score"])
                > float(current["score"])
            ):
                grouped[key] = item

        representatives = sorted(
            grouped.values(),
            key=lambda item: float(
                item["score"]
            ),
            reverse=True,
        )

        all_representatives[
            scientist
        ] = representatives

        total_representatives += len(
            representatives
        )

        print()
        print(
            "===",
            scientist.upper(),
            "===",
        )
        print(
            "RAW",
            len(items),
            "FAMILIES",
            len(grouped),
            "COLLAPSED",
            len(items)
            - len(grouped)
            - sum(
                1
                for rejected_scientist, _, _
                in rejected
                if rejected_scientist
                == scientist
            ),
            "EXACT_REJECTED",
            sum(
                1
                for rejected_scientist, _, _
                in rejected
                if rejected_scientist
                == scientist
            ),
        )

        for rank, item in enumerate(
            representatives[:5],
            start=1,
        ):
            print(
                f"{rank}.",
                _describe(
                    scientist,
                    item,
                ),
                f"score={float(item['score']):.6f}",
            )

    print()
    print(
        "TOTAL_FAMILY_REPRESENTATIVES",
        total_representatives,
    )
    print(
        "TOTAL_EXACT_REJECTED",
        len(rejected),
    )

    if rejected:
        print()
        print(
            "=== EXACT SEMANTIC REJECTIONS ==="
        )

        for scientist, reason, item in rejected:
            print(
                scientist,
                reason,
                "::",
                _describe(
                    scientist,
                    item,
                ),
            )

    print()
    print(
        "=== FIRST-PASS DIVERSE INVENTORY ==="
    )
    print(
        "One strongest family representative "
        "from each scientist; NOT a frozen batch."
    )

    for scientist, representatives in (
        all_representatives.items()
    ):
        if not representatives:
            continue

        item = representatives[0]

        print(
            scientist,
            "::",
            _describe(
                scientist,
                item,
            ),
            f"score={float(item['score']):.6f}",
        )

    print()
    print(
        "DRY_RUN_ONLY True"
    )
    print(
        "HYPOTHESES_FROZEN False"
    )
    print(
        "VALIDATION_BATCH_CREATED False"
    )
    print(
        "SEP2_ACCESSED False"
    )


if __name__ == "__main__":
    main()
