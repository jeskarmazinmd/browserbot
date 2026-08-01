#!/usr/bin/env python3
"""
trendline_scanner_v24_fix2.py
VERSION: 2026-05-10-schwab-quote-speed-test-v24

Purpose:
    Benchmark Schwab quote latency for large symbol universes.

Goal:
    Determine realistic live-refresh architecture for the flash-dip bot.

This script:
    - loads Schwab API key from:
        ~/Desktop/schwabkey.txt

    - loads symbols from:
        ~/Desktop/1Mvolumesymbols.csv

    - tests quote retrieval speed for:
        1 symbol
        10 symbols
        25 symbols
        50 symbols
        100 symbols
        250 symbols

    - prints:
        total request time
        ms per symbol
        symbols returned

Requirements:
    pip install schwab-py httpx authlib pandas

You must already have Schwab auth/token working locally.

Run:
    cd ~/Desktop
    source scannerenv/bin/activate
    python3 trendline_scanner_v24_fix2.py
"""

from pathlib import Path
import time
import pandas as pd

from schwab.auth import easy_client, client_from_token_file


from pathlib import Path
import os

BASE_DIR = Path("/app")

TOKEN_PATH = BASE_DIR / "schwab_token.json"
SYMBOL_FILE = BASE_DIR / "1Mvolumesymbols.csv"

SCHWAB_APP_KEY = os.getenv("SCHWAB_APP_KEY")
SCHWAB_SECRET = os.getenv("SCHWAB_SECRET", "")

REDIRECT_URI = "https://127.0.0.1:8182"

TEST_SIZES = [1, 10, 25, 50, 100, 250]


def load_app_key():
    """
    Supports either format:

    1)
        APPKEY:SECRET

    2)
        SCHWAB_APP_KEY=...
        SCHWAB_SECRET=...
    """
    if SCHWAB_APP_KEY:
        return SCHWAB_APP_KEY, SCHWAB_SECRET

    raise ValueError("Fly secrets not detected")

    app_key = ""
    secret = ""

    # Key-value format.
    if "SCHWAB_APP_KEY=" in txt or "SCHWAB_SECRET=" in txt:
        for line in txt.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue

            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()

            if k == "SCHWAB_APP_KEY":
                app_key = v
            elif k == "SCHWAB_SECRET":
                secret = v

    # Colon format.
    elif ":" in txt:
        app_key, secret = txt.split(":", 1)

    # App-key-only format.
    else:
        app_key = txt
        secret = ""

    app_key = app_key.strip()
    secret = secret.strip()

    if not app_key:
        raise ValueError("Could not read SCHWAB_APP_KEY from schwabkey.txt")

    if not secret:
        print("Warning: no SCHWAB_SECRET found in schwabkey.txt")

    return app_key, secret


def load_symbols():
    df = pd.read_csv(SYMBOL_FILE)

    for col in ["Ticker", "ticker", "Symbol", "symbol"]:
        if col in df.columns:
            syms = df[col].astype(str).str.upper().tolist()
            syms = [s.strip() for s in syms if s.strip()]
            return list(dict.fromkeys(syms))

    raise ValueError(f"No ticker column found. Columns: {list(df.columns)}")


def benchmark(client, symbols):
    start = time.perf_counter()

    try:
        response = client.get_quotes(symbols)
        elapsed = time.perf_counter() - start

        ok = response.status_code == 200

        try:
            data = response.json()
            returned = len(data)
        except Exception:
            returned = 0

        return {
            "ok": ok,
            "elapsed_seconds": elapsed,
            "returned_symbols": returned,
        }

    except Exception as e:
        elapsed = time.perf_counter() - start

        return {
            "ok": False,
            "elapsed_seconds": elapsed,
            "returned_symbols": 0,
            "error": str(e),
        }


def main():
    print("trendline_scanner_v24_fix2.py")
    print()

    app_key, secret = load_app_key()

    print("Loaded Schwab credentials from:")
    print()

    print("Connecting to Schwab...")

    client = client_from_token_file(
        str(TOKEN_PATH),
        app_key,
        secret,
    )

    print("Connected.")
    print()

    symbols = load_symbols()

    print(f"Loaded {len(symbols)} symbols")
    print()

    print("===== QUOTE SPEED TEST =====")
    print()

    rows = []

    for n in TEST_SIZES:
        subset = symbols[:n]

        print(f"Testing {n} symbols...")

        result = benchmark(client, subset)

        ms_per_symbol = (
            (result["elapsed_seconds"] * 1000) / n
            if n > 0 else 0
        )

        row = {
            "symbols_requested": n,
            "ok": result["ok"],
            "elapsed_seconds": result["elapsed_seconds"],
            "ms_per_symbol": ms_per_symbol,
            "returned_symbols": result["returned_symbols"],
        }

        if "error" in result:
            row["error"] = result["error"]

        rows.append(row)

        print(
            f"  elapsed: {result['elapsed_seconds']:.3f}s | "
            f"{ms_per_symbol:.2f} ms/symbol | "
            f"returned: {result['returned_symbols']}"
        )

        if "error" in result:
            print(f"  error: {result['error']}")

        print()

    out = pd.DataFrame(rows)

    outfile = Path("/app/schwab_quote_speed_test.csv")
    out.to_csv(outfile, index=False)

    print("Saved:")
    print(outfile)

    print()
    print("Interpretation:")
    print("  Lower ms/symbol = better scalability.")
    print("  If large batches scale efficiently,")
    print("  the bot can refresh broad universes quickly.")


if __name__ == "__main__":
    main()
# redeploy
