import math
import numpy as np
import pandas as pd


def clean_prices(values):
    series = pd.Series(values, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    return series[series > 0].reset_index(drop=True)


def return_pct(start, end):
    start = float(start)
    end = float(end)
    return (end / start - 1.0) * 100.0 if start > 0 else math.nan


def linear_trend(prices):
    prices = clean_prices(prices)
    if len(prices) < 5:
        return math.nan, math.nan
    y = np.log(prices.to_numpy())
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residual = float(np.sum((y - fitted) ** 2))
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - residual / total if total > 0 else 0.0
    return (math.exp(slope) - 1.0) * 100.0, r2


def safe_ratio(numerator, denominator):
    denominator = float(denominator)
    return float(numerator) / denominator if denominator else math.nan
