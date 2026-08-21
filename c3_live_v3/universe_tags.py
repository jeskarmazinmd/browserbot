"""Universe classification helpers.

This module only describes symbols. It does not filter symbols or make trading
decisions.
"""

def price_bucket(price):
    try:
        p=float(price)
    except Exception:
        return "PRICE_UNKNOWN"
    if p < 5:
        return "PRICE_UNDER_5"
    if p < 20:
        return "PRICE_5_TO_20"
    if p < 100:
        return "PRICE_20_TO_100"
    return "PRICE_OVER_100"

def liquidity_bucket(volume):
    try:
        v=float(volume)
    except Exception:
        return "LIQUIDITY_UNKNOWN"
    if v >= 10_000_000:
        return "HIGH_LIQUIDITY"
    if v >= 1_000_000:
        return "MEDIUM_LIQUIDITY"
    return "LOW_LIQUIDITY"

def volatility_bucket(vol):
    try:
        v=float(vol)
    except Exception:
        return "VOLATILITY_UNKNOWN"
    if v >= 60:
        return "HIGH_VOLATILITY"
    if v >= 25:
        return "MEDIUM_VOLATILITY"
    return "LOW_VOLATILITY"

def build_tags(row):
    tags=[]
    tags.append(price_bucket(row.get("last_price")))
    tags.append(liquidity_bucket(row.get("min_volume_last5")))
    tags.append(volatility_bucket(row.get("volatility_6m_annualized_pct")))
    if row.get("pass_longterm") is True:
        tags.append("LEGACY_LONGTERM_PASS")
    if row.get("pass_liquidity") is True:
        tags.append("LEGACY_LIQUIDITY_PASS")
    return [x for x in tags if x]
