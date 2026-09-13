"""
Adapter from real discovery-report records to generic triage candidates.

This module does not:
- access raw market data;
- access validation data;
- freeze hypotheses;
- create validation batches.

It only translates already-produced discovery records into the generic
dependence-aware shortlist policy.
"""

from __future__ import annotations

import hashlib
import json

from research_tools.module_factory.discovery_triage_policy import (
    TriageCandidate,
)
from research_tools.module_factory.hypothesis_fingerprint import (
    feature_family,
)
from research_tools.module_factory.semantic_canonicalization import (
    canonicalize_expression,
)


def _stable_candidate_id(
    scientist: str,
    item: dict,
) -> str:
    payload = {
        "scientist": scientist,
        "record": item,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        encoded.encode()
    ).hexdigest()[:20]

    return f"triage:{digest}"


def _is_return_family(
    feature: str,
) -> bool:
    return feature_family(feature) in {
        "return",
        "spy_relative_return",
    }


def _is_kurtosis_family(
    feature: str,
) -> bool:
    return (
        feature_family(feature)
        == "kurtosis"
    )


def concept_for_record(
    scientist: str,
    item: dict,
) -> str:
    if scientist == "generic":
        feature = item["feature"]

        if _is_return_family(feature):
            return "plain-return-momentum"

        return (
            "generic:"
            f"{feature_family(feature)}"
        )

    if scientist == "cross_sectional":
        feature = item["feature"]

        if _is_return_family(feature):
            return "cross-sectional-return"

        return (
            "cross-sectional:"
            f"{feature_family(feature)}"
        )

    if scientist == "conditional":
        signal = item["signal_feature"]
        state = item["state_feature"]

        if (
            _is_return_family(signal)
            and _is_kurtosis_family(state)
        ):
            return "return-kurtosis-state"

        return (
            "conditional:"
            f"{feature_family(signal)}:"
            f"{feature_family(state)}:"
            f"{item['state_direction']}"
        )

    if scientist == "regime":
        signal = item["feature"]
        regime = item["regime_feature"]

        if (
            _is_return_family(signal)
            and _is_kurtosis_family(regime)
        ):
            return "return-kurtosis-state"

        return (
            "regime:"
            f"{feature_family(signal)}:"
            f"{feature_family(regime)}:"
            f"reversal={bool(item['sign_reversal'])}"
        )

    if scientist == "distribution":
        feature = item["feature"]

        if _is_return_family(feature):
            if (
                item["dominant_effect"]
                == "large_move"
            ):
                return "return-large-move-state"

            return "return-distribution-state"

        return (
            "distribution:"
            f"{feature_family(feature)}:"
            f"{item['dominant_effect']}"
        )

    if scientist == "residual":
        candidate = item["candidate"]
        family = feature_family(candidate)

        if family == "skew":
            return "residual-skew"

        if family == "acceleration":
            return "residual-acceleration"

        if _is_return_family(candidate):
            return "residual-return"

        return f"residual:{family}"

    if scientist == "time_series":
        feature = item["feature"]
        family = feature_family(feature)

        if (
            family == "acceleration"
            and bool(item["sign_change"])
        ):
            return (
                "acceleration-lag-reversal"
            )

        if _is_return_family(feature):
            return "return-lag"

        return f"time-series:{family}"

    if scientist == "anomaly":
        features = tuple(
            item["features"]
        )

        families = {
            feature_family(feature)
            for feature in features
        }

        if (
            "kurtosis" in families
            and (
                "return" in families
                or "spy_relative_return"
                in families
            )
            and item["dominant_effect"]
            == "large_move"
        ):
            return "large-move-anomaly"

        return (
            "anomaly:"
            + ",".join(
                sorted(families)
            )
            + ":"
            + str(item["dominant_effect"])
        )

    if scientist == "interaction":
        left = item["left"]
        right = item["right"]

        families = sorted(
            (
                feature_family(left),
                feature_family(right),
            )
        )

        return (
            "interaction:"
            f"{item['operation']}:"
            + ",".join(families)
        )

    raise ValueError(
        f"unsupported scientist: {scientist}"
    )


def _exact_redundant(
    scientist: str,
    item: dict,
) -> bool:
    if scientist != "interaction":
        return False

    expression = canonicalize_expression(
        operation=item["operation"],
        left=item["left"],
        right=item["right"],
    )

    return (
        expression.operation
        == "market_return"
    )


def _independent_time_units(
    scientist: str,
    item: dict,
) -> int:
    if scientist == "cross_sectional":
        return int(
            item["minutes"]
        )

    if "independent_time_units" in item:
        return int(
            item["independent_time_units"]
        )

    # Legacy reports without measured time support
    # must fail conservatively rather than receiving
    # invented evidence.
    return 0


def _incremental_evidence(
    scientist: str,
    item: dict,
) -> float | None:
    if scientist == "interaction":
        return float(
            item["incremental_edge"]
        )

    if scientist == "conditional":
        return float(
            item["improvement"]
        )

    if scientist == "residual":
        return float(
            item["incremental_clarity"]
        )

    if scientist == "time_series":
        return float(
            item["incremental_lag_edge"]
        )

    return None


def triage_candidate_from_record(
    scientist: str,
    item: dict,
) -> TriageCandidate:
    return TriageCandidate(
        candidate_id=_stable_candidate_id(
            scientist,
            item,
        ),
        scientist=scientist,
        concept=concept_for_record(
            scientist,
            item,
        ),
        score=float(
            item["score"]
        ),
        independent_time_units=(
            _independent_time_units(
                scientist,
                item,
            )
        ),
        incremental_evidence=(
            _incremental_evidence(
                scientist,
                item,
            )
        ),
        sign_change=bool(
            item.get(
                "sign_change",
                False,
            )
            or (
                scientist == "regime"
                and item.get(
                    "sign_reversal",
                    False,
                )
            )
        ),
        exact_redundant=(
            _exact_redundant(
                scientist,
                item,
            )
        ),
    )
