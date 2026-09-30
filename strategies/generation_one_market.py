"""Fresh raw-market trend predicate for cross-cadence flash confirmation."""
from . import generation_one as flash, generation_one_minute as minute


def enrich_confirmation(signal, frame):
    sid = signal["strategy_id"]
    if sid not in {"G1PQT2", "G1PQT3"}:
        return signal
    import pandas as pd
    row = dict(signal)
    row["frozen_trend_vote"] = False
    symbol = signal["symbol"]
    if symbol not in minute.UNIVERSE:
        return row
    end = pd.Timestamp(signal["timestamp"]).floor("min") - pd.Timedelta(minutes=1)
    start = end - pd.Timedelta(minutes=30)
    own = frame.loc[frame["symbol"] == symbol, ["timestamp", "price"]].copy()
    own["timestamp"] = pd.to_datetime(own["timestamp"], utc=True, errors="coerce")
    own = own[(own["timestamp"] >= start) & (own["timestamp"] < end + pd.Timedelta(minutes=1))]
    own["minute"] = own["timestamp"].dt.floor("min")
    prices = own.sort_values("timestamp").groupby("minute")["price"].last().reindex(pd.date_range(start, end, freq="min"))
    if prices.isna().any() or any(flash.num(price) <= 0 for price in prices):
        return row
    # Explicit frozen thresholds; this does not consult another child catalog.
    rule = minute.MinuteExperiment("frozen_hybrid", "raw trend gate", ("TREND",), 1,
                                   .9, .65, ret30=1.2, ret5=.25, up_fraction=.58)
    votes, _, metrics = minute.predicates(rule, list(prices))
    row.update(frozen_trend_vote=bool(votes), frozen_trend_timestamp=end.isoformat(),
               frozen_trend_metrics=metrics)
    return row
