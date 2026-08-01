from pathlib import Path
from datetime import datetime, timezone
import time
import pandas as pd

LOOKBACK_PERIOD = "1d"
INTERVAL = "1m"
MAX_AGE_MINUTES = 60
CHUNK_SIZE = 50

def load_symbols():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = [
        Path("/data") / f"eligible_symbols_{today}.csv",
        Path(f"eligible_symbols_{today}.csv"),
        Path("/app") / f"eligible_symbols_{today}.csv",
    ]

    for base in [Path("/data"), Path("/app"), Path(".")]:
        candidates.extend(sorted(base.glob("eligible_symbols_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True))

    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            df = pd.read_csv(p)
            syms = df["symbol"].astype(str).dropna().unique().tolist()
            print(f"Backfill using symbols from {p}: {len(syms)} symbols", flush=True)
            return syms

    raise FileNotFoundError("No eligible_symbols_*.csv found")

def main():
    import yfinance as yf

    symbols = load_symbols()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = Path("/data/tapes") / f"quotes_{today}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=MAX_AGE_MINUTES)

    for i in range(0, len(symbols), CHUNK_SIZE):
        chunk = symbols[i:i + CHUNK_SIZE]
        print(f"Backfill chunk {i//CHUNK_SIZE + 1}: {len(chunk)} symbols", flush=True)

        try:
            data = yf.download(
                tickers=" ".join(chunk),
                period=LOOKBACK_PERIOD,
                interval=INTERVAL,
                progress=False,
                auto_adjust=False,
                threads=True,
                group_by="ticker",
            )
        except Exception as e:
            print(f"Backfill chunk error: {type(e).__name__}: {e}", flush=True)
            continue

        for sym in chunk:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if sym not in data.columns.get_level_values(0):
                        continue
                    close = data[sym]["Close"].dropna()
                else:
                    close = data["Close"].dropna()

                close.index = pd.to_datetime(close.index, utc=True)
                close = close[close.index >= cutoff]

                for ts, px in close.items():
                    if pd.notna(px) and float(px) > 0:
                        rows.append({
                            "timestamp": ts.isoformat(),
                            "symbol": sym,
                            "price": float(px),
                        })
            except Exception:
                continue

        time.sleep(0.2)

    if not rows:
        print("Backfill produced no rows; continuing anyway.", flush=True)
        return

    new = pd.DataFrame(rows)

    if out.exists() and out.stat().st_size > 0:
        old = pd.read_csv(out)
        combined = pd.concat([old, new], ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
    else:
        combined = new

    combined = combined.sort_values(["timestamp", "symbol"])
    combined.to_csv(out, index=False)

    print(f"Backfill wrote {len(new)} rows; tape now has {len(combined)} rows: {out}", flush=True)

if __name__ == "__main__":
    main()
