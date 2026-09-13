"""
Microstructure features derived from sampled Level-1 observations.

These are snapshot features. They must not be interpreted as
complete order-flow, volume, or order-book histories.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from research_tools.module_factory.market_observations import (
    MarketObservation,
)


@dataclass(frozen=True)
class MicrostructureFeatures:
    midpoint: float
    spread: float
    spread_bps: float

    quoted_depth: float
    depth_imbalance: float
    microprice: float
    microprice_displacement_bps: float

    last_vs_mid_bps: float
    mark_vs_mid_bps: float

    quote_age_ms: float
    trade_age_ms: float
    bid_age_ms: float
    ask_age_ms: float

    side_age_imbalance_ms: float
    quote_trade_age_gap_ms: float

    last_size_share: float

    bid_ask_same_venue: float
    trade_bid_same_venue: float
    trade_ask_same_venue: float


def _finite(*values: float) -> bool:
    return all(
        math.isfinite(value)
        for value in values
    )


def _ratio(
    numerator: float,
    denominator: float,
) -> float:
    if (
        not _finite(
            numerator,
            denominator,
        )
        or abs(denominator) < 1e-12
    ):
        return math.nan

    return numerator / denominator


def _age(
    observed_at_ms: int | None,
    event_ms: int | None,
) -> float:
    if (
        observed_at_ms is None
        or event_ms is None
    ):
        return math.nan

    return float(
        observed_at_ms - event_ms
    )


def _venue_match(
    left: str,
    right: str,
) -> float:
    if not left or not right:
        return math.nan

    return float(left == right)


def derive_microstructure_features(
    observation: MarketObservation,
) -> MicrostructureFeatures:
    bid = observation.bid
    ask = observation.ask

    midpoint = (
        (bid + ask) / 2.0
        if _finite(bid, ask)
        else math.nan
    )

    spread = (
        ask - bid
        if _finite(bid, ask)
        else math.nan
    )

    spread_bps = (
        10000.0
        * _ratio(
            spread,
            midpoint,
        )
    )

    quoted_depth = (
        observation.bid_size
        + observation.ask_size
        if _finite(
            observation.bid_size,
            observation.ask_size,
        )
        else math.nan
    )

    depth_imbalance = _ratio(
        observation.bid_size
        - observation.ask_size,
        quoted_depth,
    )

    # Standard top-of-book microprice convention:
    # stronger bid depth pulls estimated fair price toward ask,
    # and stronger ask depth pulls it toward bid.
    microprice = _ratio(
        (
            ask * observation.bid_size
            + bid * observation.ask_size
        ),
        quoted_depth,
    )

    microprice_displacement_bps = (
        10000.0
        * _ratio(
            microprice - midpoint,
            midpoint,
        )
    )

    last_vs_mid_bps = (
        10000.0
        * _ratio(
            observation.last - midpoint,
            midpoint,
        )
    )

    mark_vs_mid_bps = (
        10000.0
        * _ratio(
            observation.mark - midpoint,
            midpoint,
        )
    )

    observed = observation.observed_at_ms

    quote_age_ms = _age(
        observed,
        observation.quote_time_ms,
    )
    trade_age_ms = _age(
        observed,
        observation.trade_time_ms,
    )
    bid_age_ms = _age(
        observed,
        observation.bid_time_ms,
    )
    ask_age_ms = _age(
        observed,
        observation.ask_time_ms,
    )

    side_age_imbalance_ms = (
        bid_age_ms - ask_age_ms
        if _finite(
            bid_age_ms,
            ask_age_ms,
        )
        else math.nan
    )

    quote_trade_age_gap_ms = (
        quote_age_ms - trade_age_ms
        if _finite(
            quote_age_ms,
            trade_age_ms,
        )
        else math.nan
    )

    total_visible_activity = (
        observation.last_size
        + observation.bid_size
        + observation.ask_size
        if _finite(
            observation.last_size,
            observation.bid_size,
            observation.ask_size,
        )
        else math.nan
    )

    last_size_share = _ratio(
        observation.last_size,
        total_visible_activity,
    )

    return MicrostructureFeatures(
        midpoint=midpoint,
        spread=spread,
        spread_bps=spread_bps,
        quoted_depth=quoted_depth,
        depth_imbalance=depth_imbalance,
        microprice=microprice,
        microprice_displacement_bps=(
            microprice_displacement_bps
        ),
        last_vs_mid_bps=last_vs_mid_bps,
        mark_vs_mid_bps=mark_vs_mid_bps,
        quote_age_ms=quote_age_ms,
        trade_age_ms=trade_age_ms,
        bid_age_ms=bid_age_ms,
        ask_age_ms=ask_age_ms,
        side_age_imbalance_ms=(
            side_age_imbalance_ms
        ),
        quote_trade_age_gap_ms=(
            quote_trade_age_gap_ms
        ),
        last_size_share=last_size_share,
        bid_ask_same_venue=_venue_match(
            observation.bid_mic,
            observation.ask_mic,
        ),
        trade_bid_same_venue=_venue_match(
            observation.last_mic,
            observation.bid_mic,
        ),
        trade_ask_same_venue=_venue_match(
            observation.last_mic,
            observation.ask_mic,
        ),
    )
