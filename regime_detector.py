from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd


def _simple_return_pct(start, end):
    try:
        start = float(start)
        end = float(end)
        if start <= 0:
            return None
        return (end / start - 1.0) * 100.0
    except Exception:
        return None


def _fit_log_slope(prices):
    prices = pd.Series(prices).dropna().astype(float)
    prices = prices[prices > 0]

    if len(prices) < 5:
        return None, None

    y = np.log(prices.to_numpy())
    x = np.arange(len(y), dtype=float)

    try:
        slope, _ = np.polyfit(x, y, 1)
    except Exception:
        return None, None

    y_hat = slope * x + np.mean(y)

    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)

    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

    return float((math.exp(slope) - 1) * 100), float(r2) if r2 is not None else None


def _series_return(series, minutes):
    if len(series) <= minutes:
        return None

    start = float(series.iloc[-minutes - 1])
    end = float(series.iloc[-1])

    return _simple_return_pct(start, end)


def _session_phase(ts):
    try:
        hour = ts.hour
        minute = ts.minute
        total = hour * 60 + minute

        if total < 16 * 60:
            return "PREMARKET"
        if total < 10 * 60 + 30:
            return "OPEN"
        if total < 12 * 60:
            return "MORNING"
        if total < 14 * 60:
            return "MIDDAY"
        if total < 15 * 60 + 30:
            return "AFTERNOON"

        return "CLOSE"
    except Exception:
        return None


def calculate_regime(df, timestamp=None):
    """
    Calculate broad market regime features.

    This function only observes.
    It does not make trading decisions.
    """

    if df is None or len(df) == 0:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "empty_dataframe",
        }

    df = df.copy()
    df["symbol"] = df["symbol"].astype(str)

    if timestamp is None:
        timestamp = df["timestamp"].max()

    if isinstance(timestamp, str):
        timestamp = pd.Timestamp(timestamp)

    result = {
        "timestamp": str(timestamp),
        "returns": {},
        "trend": {},
        "volatility": {},
        "breadth": {},
        "dispersion": {},
        "correlation": {},
        "data_quality": {},
        "labels": {},
    }

    result["data_quality"] = {
        "symbols_available": int(df["symbol"].nunique()),
        "minutes_available": int(df["timestamp"].nunique()),
        "quality": (
            "GOOD"
            if int(df["timestamp"].nunique()) >= 60
            else "LIMITED"
        ),
    }


    # ------------------------
    # Index direction
    # ------------------------

    for symbol in ["SPY", "QQQ", "IWM"]:

        g = (
            df[df["symbol"] == symbol]
            .sort_values("timestamp")
        )

        if len(g):

            prices = g["price"].astype(float)

            result["returns"][symbol] = {
                "1m": _series_return(prices, 1),
                "5m": _series_return(prices, 5),
                "15m": _series_return(prices, 15),
                "30m": _series_return(prices, 30),
            }


    # ------------------------
    # SPY trend
    # ------------------------

    spy = df[df["symbol"] == "SPY"].sort_values("timestamp")

    if len(spy):

        spy_prices = spy["price"].astype(float)

        slope, r2 = _fit_log_slope(
            spy_prices.tail(31)
        )

        if slope is None:
            trend_label = "UNKNOWN"
        elif slope > 0.10 and (r2 or 0) > 0.4:
            trend_label = "UPTREND"
        elif slope < -0.10 and (r2 or 0) > 0.4:
            trend_label = "DOWNTREND"
        else:
            trend_label = "CHOP"

        result["trend"] = {
            "spy_slope_30m": slope,
            "spy_r2_30m": r2,
            "classification": trend_label,
        }


    # ------------------------
    # Breadth
    # ------------------------

    latest_rows = (
        df.sort_values("timestamp")
        .groupby("symbol")
        .tail(31)
    )

    returns = []

    for symbol, g in latest_rows.groupby("symbol"):

        prices = g.sort_values("timestamp")["price"].astype(float)

        if len(prices) >= 6:

            ret = _series_return(prices, 5)

            if ret is not None:
                returns.append(ret)


    if returns:

        arr = np.array(returns)

        result["breadth"] = {
            "symbols_measured": len(arr),
            "green_pct_5m": float(np.mean(arr > 0) * 100),
            "red_pct_5m": float(np.mean(arr < 0) * 100),
            "median_return_5m": float(np.median(arr)),
            "average_return_5m": float(np.mean(arr)),
        }


        # dispersion

        result["dispersion"] = {
            "top10_avg": float(np.mean(np.sort(arr)[-10:])),
            "bottom10_avg": float(np.mean(np.sort(arr)[:10])),
            "spread": float(
                np.mean(np.sort(arr)[-10:])
                -
                np.mean(np.sort(arr)[:10])
            ),
            "std": float(np.std(arr)),
        }


    # ------------------------
    # Volatility
    # ------------------------

    if len(spy):

        spy_returns = (
            spy["price"]
            .astype(float)
            .pct_change()
            .dropna()
        )

        vol = (
            float(spy_returns.tail(30).std())
            if len(spy_returns)
            else None
        )

        if vol is None:
            vol_label = "UNKNOWN"
        elif vol > 0.004:
            vol_label = "HIGH"
        elif vol < 0.001:
            vol_label = "LOW"
        else:
            vol_label = "NORMAL"

        result["volatility"] = {
            "spy_30m_std": vol,
            "classification": vol_label,
        }


    # ------------------------
    # Labels
    # ------------------------

    spy30 = (
        result["returns"]
        .get("SPY", {})
        .get("30m")
    )

    if spy30 is not None:

        if spy30 > 0.3:
            direction = "UP"
        elif spy30 < -0.3:
            direction = "DOWN"
        else:
            direction = "FLAT"

        result["labels"]["direction"] = direction


    green = result["breadth"].get("green_pct_5m")

    if green is None:
        result["labels"]["breadth"] = "UNKNOWN"
    elif green < 25:
        result["labels"]["breadth"] = "BROAD_SELLING"
    elif green > 75:
        result["labels"]["breadth"] = "BROAD_BUYING"
    else:
        result["labels"]["breadth"] = "MIXED"


    if timestamp is not None:
        result["labels"]["session_phase"] = _session_phase(
            pd.Timestamp(timestamp)
        )

    return result
