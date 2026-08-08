"""Adaptive cross-symbol research with strict temporal/data-quality gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd


NY=ZoneInfo("America/New_York")


@dataclass(frozen=True)
class XSDataEligibility:
    state: str
    reason: str
    regular_minutes: int
    total_minutes: int
    symbols: int

    @property
    def eligible(self):
        return self.state=="ELIGIBLE"


def _timestamp_column(frame):
    for name in ("market_minute_utc","timestamp"):
        if name in frame.columns:
            return name
    return None


def assess_minute_data(
    frame,
    *,
    min_regular_minutes=300,
    min_symbols=100,
):
    """Fail closed unless a dataset contains substantial regular-session data."""
    ts_col=_timestamp_column(frame)

    if ts_col is None or "symbol" not in frame.columns:
        return XSDataEligibility(
            "INVALID",
            "timestamp/symbol schema missing",
            0,
            0,
            0,
        )

    timestamps=pd.to_datetime(
        frame[ts_col],
        errors="coerce",
        utc=True,
    ).dropna()

    if timestamps.empty:
        return XSDataEligibility(
            "INVALID",
            "no valid timestamps",
            0,
            0,
            0,
        )

    unique=pd.Series(timestamps.unique())
    local=unique.dt.tz_convert(NY)

    regular=(
        (local.dt.weekday < 5)
        & (local.dt.time >= time(9,30))
        & (local.dt.time < time(16,0))
    )

    regular_minutes=int(regular.sum())
    total_minutes=int(len(unique))
    symbols=int(frame["symbol"].nunique())

    if regular_minutes < int(min_regular_minutes):
        return XSDataEligibility(
            "FIXTURE_ONLY",
            "insufficient regular-session minute coverage",
            regular_minutes,
            total_minutes,
            symbols,
        )

    if symbols < int(min_symbols):
        return XSDataEligibility(
            "FIXTURE_ONLY",
            "insufficient cross-sectional symbol coverage",
            regular_minutes,
            total_minutes,
            symbols,
        )

    return XSDataEligibility(
        "ELIGIBLE",
        "substantial regular-session cross-sectional market path",
        regular_minutes,
        total_minutes,
        symbols,
    )


def regular_session_only(frame):
    """Return observations knowable during regular US market minutes."""
    ts_col=_timestamp_column(frame)
    if ts_col is None:
        raise ValueError("timestamp column missing")

    work=frame.copy()
    work[ts_col]=pd.to_datetime(
        work[ts_col],
        errors="coerce",
        utc=True,
    )
    work=work.dropna(subset=[ts_col])

    local=work[ts_col].dt.tz_convert(NY)

    keep=(
        (local.dt.weekday < 5)
        & (local.dt.time >= time(9,30))
        & (local.dt.time < time(16,0))
    )
    return work.loc[keep].copy()
