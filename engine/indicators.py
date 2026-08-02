from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None

    alpha = 2.0 / (period + 1.0)

    e = sum(values[:period]) / period

    for v in values[period:]:
        e = alpha * v + (1.0 - alpha) * e

    return e


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []

    alpha = 2.0 / (period + 1.0)

    out = []

    e = sum(values[:period]) / period
    out.extend([None] * (period - 1))
    out.append(e)

    for v in values[period:]:
        e = alpha * v + (1.0 - alpha) * e
        out.append(e)

    return out


def highest(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return max(values[-period:])


def lowest(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return min(values[-period:])


def simple_return(start: float, end: float) -> float | None:
    if start <= 0:
        return None
    return (end / start - 1.0) * 100.0
