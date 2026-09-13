"""Fast reusable cascade feature extraction for Module Factory.

The expensive traversal of minute bars is performed once for each window size.
Candidate parameter combinations then filter the resulting observations rather
than rescanning every symbol for every candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from research_tools.cascade_reversal_study import Bar


@dataclass(frozen=True)
class CascadeObservation:
    symbol: str
    minute: datetime
    window_minutes: int
    entry: float
    cascade_pct: float
    down_minutes: int
    max_down_minute_pct: float
    distance_from_low_bps: float
    spy_cascade_pct: float | None
    returns: dict[int, float]


def _contiguous(bars: list[Bar], start: int, end: int) -> bool:
    return all(
        bars[i].minute - bars[i - 1].minute == timedelta(minutes=1)
        for i in range(start + 1, end + 1)
    )


def _cascade(window: list[Bar]) -> float:
    peak = max(bar.high for bar in window)
    trough = min(bar.low for bar in window)
    return 100.0 * (trough / peak - 1.0)


def extract_observations(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    window_minutes: int,
    horizons: tuple[int, ...] = (10, 20),
) -> list[CascadeObservation]:
    """Extract every confirmed cascade-shaped observation before thresholds."""

    observations: list[CascadeObservation] = []
    spy_by_minute = {
        bar.minute: bar
        for bar in bars_by_symbol.get("SPY", [])
    }

    longest = max(horizons)

    for symbol, bars in sorted(bars_by_symbol.items()):
        if symbol == "SPY" or len(bars) <= window_minutes + longest:
            continue

        for index in range(window_minutes, len(bars) - longest):
            start = index - window_minutes

            if not _contiguous(bars, start, index + longest):
                continue

            prior = bars[start:index]
            confirmation = bars[index]
            prior_close = bars[index - 1].close

            # Same confirmation rule as cascade_reversal_study.detect_events().
            if confirmation.close <= prior_close:
                continue

            minute_returns = [
                100.0 * (bars[pos].close / bars[pos - 1].close - 1.0)
                for pos in range(start + 1, index)
            ]

            rolling_low = min(bar.low for bar in prior)
            distance_from_low_bps = (
                10000.0 * (prior_close / rolling_low - 1.0)
            )

            spy_window = [
                spy_by_minute.get(bar.minute)
                for bar in prior
            ]

            spy_cascade = None
            if all(spy_window):
                spy_cascade = _cascade(
                    [bar for bar in spy_window if bar is not None]
                )

            entry = confirmation.close

            observations.append(
                CascadeObservation(
                    symbol=symbol,
                    minute=confirmation.minute,
                    window_minutes=window_minutes,
                    entry=entry,
                    cascade_pct=_cascade(prior),
                    down_minutes=sum(value < 0 for value in minute_returns),
                    max_down_minute_pct=(
                        min(minute_returns) if minute_returns else 0.0
                    ),
                    distance_from_low_bps=distance_from_low_bps,
                    spy_cascade_pct=spy_cascade,
                    returns={
                        horizon: 100.0 * (
                            bars[index + horizon].close / entry - 1.0
                        )
                        for horizon in horizons
                    },
                )
            )

    return observations


def filter_observations(
    observations: list[CascadeObservation],
    *,
    min_drop_pct: float,
    min_down_minutes: int,
    near_low_bps: float,
    max_single_minute_drop_pct: float,
    max_spy_drop_pct: float,
    cooldown_minutes: int,
) -> list[CascadeObservation]:
    """Apply candidate thresholds and reproduce detector cooldown semantics."""

    accepted: list[CascadeObservation] = []
    last_event_by_symbol: dict[str, datetime] = {}

    for obs in observations:
        if obs.cascade_pct > -min_drop_pct:
            continue

        if obs.down_minutes < min_down_minutes:
            continue

        if obs.max_down_minute_pct < -max_single_minute_drop_pct:
            continue

        if obs.distance_from_low_bps > near_low_bps:
            continue

        if (
            obs.spy_cascade_pct is not None
            and obs.spy_cascade_pct < -max_spy_drop_pct
        ):
            continue

        last_event = last_event_by_symbol.get(obs.symbol)
        if (
            last_event is not None
            and obs.minute - last_event < timedelta(minutes=cooldown_minutes)
        ):
            continue

        accepted.append(obs)
        last_event_by_symbol[obs.symbol] = obs.minute

    return accepted
