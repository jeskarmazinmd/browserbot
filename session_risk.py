import pandas as pd
import numpy as np
from datetime import time

df = pd.read_csv("regime_test_trades_20260510_002833.csv")

t = [c for c in df.columns if "time" in c][0]
df[t] = pd.to_datetime(df[t], errors="coerce")

df["regular"] = df[t].dt.time.between(time(9,30), time(16,0))

df = df.dropna(subset=["trade_return_pct"])

def calc(x):
    r = x["trade_return_pct"] / 100 if x["trade_return_pct"].max() > 1 else x["trade_return_pct"]
    m = r.mean()
    v = r.std()
    sh = (m / v) * np.sqrt(len(r)) if v != 0 else 0
    cum = (1 + r).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    return {
        "trades": len(x),
        "avg_return": m,
        "volatility": v,
        "sharpe_proxy": sh,
        "max_drawdown": dd
    }

regular = df[df["regular"]]
extended = df[~df["regular"]]

print("\nREGULAR HOURS")
print(calc(regular))

print("\nEXTENDED HOURS")
print(calc(extended))
