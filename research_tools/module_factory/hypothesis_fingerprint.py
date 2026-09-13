"""
Scientific hypothesis-family fingerprints for Module Factory.

These fingerprints are intentionally broader than exact semantic
canonicalization.

Purpose
-------
Group discoveries that test substantially the same scientific idea so
that nearby variants compete for one validation slot instead of all
consuming pristine validation capacity.

This module does NOT declare hypotheses mathematically equivalent.
Exact specifications remain separate and must still be frozen
individually if selected.

Examples of intended grouping:
- return_20 and return_30 -> same medium return family
- nearby regime quantiles -> same regime family
- lag 8 and lag 10 -> same delayed-lag neighborhood

Examples intentionally kept distinct:
- return vs SPY-relative return
- low-state vs high-state condition
- sign reversal vs one-sided regime
- lag 0 vs lag 10
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


_TRAILING_LOOKBACK_RE = re.compile(
    r"^(.*)_(\d+)$"
)


@dataclass(frozen=True)
class HypothesisFingerprint:
    kind: str
    payload: tuple[tuple[str, object], ...]

    @property
    def family_key(self) -> str:
        canonical = {
            "kind": self.kind,
            "payload": [
                [key, value]
                for key, value in self.payload
            ],
        }

        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        )

        digest = hashlib.sha256(
            encoded.encode()
        ).hexdigest()[:20]

        return f"family:{digest}"


def _fingerprint(
    kind: str,
    **values,
) -> HypothesisFingerprint:
    normalized = tuple(
        sorted(
            values.items(),
            key=lambda item: item[0],
        )
    )

    return HypothesisFingerprint(
        kind=kind,
        payload=normalized,
    )


def _split_feature(
    feature: str,
) -> tuple[str, int | None]:
    match = _TRAILING_LOOKBACK_RE.fullmatch(
        feature
    )

    if match is None:
        return feature, None

    family = match.group(1)
    lookback = int(match.group(2))

    return family, lookback


def feature_family(
    feature: str,
) -> str:
    family, _ = _split_feature(feature)
    return family


def _timescale_bucket_from_lookback(
    lookback: int | None,
) -> str:
    if lookback is None:
        return "none"

    if lookback <= 5:
        return "very_short"

    if lookback <= 15:
        return "short"

    if lookback <= 30:
        return "medium"

    return "long"


def feature_timescale_bucket(
    feature: str,
) -> str:
    _, lookback = _split_feature(feature)

    return _timescale_bucket_from_lookback(
        lookback
    )


def _feature_signature(
    feature: str,
) -> tuple[str, str]:
    return (
        feature_family(feature),
        feature_timescale_bucket(feature),
    )


def _lag_bucket(
    lag: int,
) -> str:
    if lag < 0:
        raise ValueError(
            "lag cannot be negative"
        )

    if lag == 0:
        return "contemporaneous"

    if lag <= 3:
        return "very_short_delay"

    if lag <= 6:
        return "short_delay"

    if lag <= 12:
        return "medium_delay"

    return "long_delay"


def fingerprint_conditional(
    *,
    signal_feature: str,
    state_feature: str,
    horizon: int,
    state_direction: str,
    preferred_sign: int,
) -> HypothesisFingerprint:
    signal_family, signal_scale = (
        _feature_signature(
            signal_feature
        )
    )

    state_family, state_scale = (
        _feature_signature(
            state_feature
        )
    )

    return _fingerprint(
        "conditional",
        signal_family=signal_family,
        signal_scale=signal_scale,
        state_family=state_family,
        state_scale=state_scale,
        horizon=horizon,
        state_direction=state_direction,
        direction=preferred_sign,
    )


def fingerprint_regime(
    *,
    feature: str,
    regime_feature: str,
    horizon: int,
    dominant_regime: str,
    direction_low: int,
    direction_high: int,
    sign_reversal: bool,
) -> HypothesisFingerprint:
    signal_family, signal_scale = (
        _feature_signature(feature)
    )

    regime_family, regime_scale = (
        _feature_signature(
            regime_feature
        )
    )

    return _fingerprint(
        "regime",
        signal_family=signal_family,
        signal_scale=signal_scale,
        regime_family=regime_family,
        regime_scale=regime_scale,
        horizon=horizon,
        dominant_regime=dominant_regime,
        direction_low=direction_low,
        direction_high=direction_high,
        sign_reversal=bool(
            sign_reversal
        ),
    )


def fingerprint_distribution(
    *,
    feature: str,
    horizon: int,
    dominant_effect: str,
    direction_low: int,
    direction_high: int,
) -> HypothesisFingerprint:
    family, scale = (
        _feature_signature(feature)
    )

    return _fingerprint(
        "distribution",
        feature_family=family,
        feature_scale=scale,
        horizon=horizon,
        dominant_effect=dominant_effect,
        direction_low=direction_low,
        direction_high=direction_high,
    )


def fingerprint_residual(
    *,
    candidate: str,
    controls: tuple[str, ...],
    horizon: int,
    direction: int,
) -> HypothesisFingerprint:
    candidate_family, candidate_scale = (
        _feature_signature(candidate)
    )

    control_signatures = tuple(
        sorted(
            _feature_signature(control)
            for control in controls
        )
    )

    return _fingerprint(
        "residual",
        candidate_family=candidate_family,
        candidate_scale=candidate_scale,
        controls=control_signatures,
        horizon=horizon,
        direction=direction,
    )


def fingerprint_time_series(
    *,
    feature: str,
    horizon: int,
    best_lag: int,
    direction: int,
    sign_change: bool,
) -> HypothesisFingerprint:
    family, scale = (
        _feature_signature(feature)
    )

    return _fingerprint(
        "time_series",
        feature_family=family,
        feature_scale=scale,
        horizon=horizon,
        lag_bucket=_lag_bucket(
            best_lag
        ),
        direction=direction,
        sign_change=bool(
            sign_change
        ),
    )


def fingerprint_anomaly(
    *,
    features: tuple[str, ...],
    horizon: int,
    dominant_effect: str,
    direction: int,
) -> HypothesisFingerprint:
    signatures = tuple(
        sorted(
            _feature_signature(feature)
            for feature in features
        )
    )

    return _fingerprint(
        "anomaly",
        features=signatures,
        horizon=horizon,
        dominant_effect=dominant_effect,
        direction=direction,
    )
