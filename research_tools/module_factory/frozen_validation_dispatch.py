"""
Dispatch sealed Factory hypotheses to exact frozen validators.

This module performs no dataset access and no discovery.
"""

from __future__ import annotations

from research_tools.module_factory.frozen_validation import (
    validate_fixed_anomaly_large_move,
    validate_fixed_distribution_mean,
    validate_fixed_lag,
    validate_fixed_regime,
    validate_fixed_residual_claim,
)


def _parameters(spec):
    return dict(spec.parameters)


def validate_frozen_specification(
    frozen,
    rows,
):
    spec = frozen.specification
    params = _parameters(spec)

    if spec.scientist == "regime":
        if len(spec.features) != 2:
            raise ValueError(
                "regime hypothesis requires "
                "feature + regime feature"
            )

        if not params.get(
            "sign_reversal",
            False,
        ):
            raise ValueError(
                "Batch-1 regime hypothesis "
                "must freeze sign reversal"
            )

        return validate_fixed_regime(
            rows,
            feature=spec.features[0],
            regime_feature=spec.features[1],
            horizon=spec.horizon,
            low_threshold=float(
                params["low_threshold"]
            ),
            high_threshold=float(
                params["high_threshold"]
            ),
            direction_low=int(
                params["direction_low"]
            ),
            direction_high=int(
                params["direction_high"]
            ),
        )

    if spec.scientist == "time_series":
        if len(spec.features) != 1:
            raise ValueError(
                "time-series hypothesis "
                "requires one feature"
            )

        return validate_fixed_lag(
            rows,
            feature=spec.features[0],
            horizon=spec.horizon,
            lag=int(params["lag"]),
            direction=int(spec.direction),
        )

    if spec.scientist == "distribution":
        if len(spec.features) != 1:
            raise ValueError(
                "distribution hypothesis "
                "requires one feature"
            )

        if params["dominant_effect"] != "mean":
            raise ValueError(
                "unsupported frozen "
                "distribution endpoint"
            )

        return validate_fixed_distribution_mean(
            rows,
            feature=spec.features[0],
            horizon=spec.horizon,
            low_threshold=float(
                params["low_threshold"]
            ),
            high_threshold=float(
                params["high_threshold"]
            ),
            direction_low=int(
                params["direction_low"]
            ),
            direction_high=int(
                params["direction_high"]
            ),
        )

    if spec.scientist == "residual":
        candidate = params["candidate"]
        controls = tuple(
            params["controls"]
        )

        if spec.features != (
            candidate,
            *controls,
        ):
            raise ValueError(
                "residual frozen feature "
                "identity mismatch"
            )

        return validate_fixed_residual_claim(
            rows,
            candidate=candidate,
            controls=controls,
            horizon=spec.horizon,
            expected_direction=int(
                spec.direction
            ),
        )

    if spec.scientist == "anomaly":
        if (
            params["dominant_effect"]
            != "large_move"
        ):
            raise ValueError(
                "unsupported frozen "
                "anomaly endpoint"
            )

        return validate_fixed_anomaly_large_move(
            rows,
            features=tuple(spec.features),
            horizon=spec.horizon,
            anomaly_threshold=float(
                params["anomaly_threshold"]
            ),
            move_threshold=float(
                params["move_threshold"]
            ),
            expected_direction=int(
                spec.direction
            ),
        )

    raise ValueError(
        "unsupported frozen scientist: "
        f"{spec.scientist}"
    )
