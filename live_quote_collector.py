import time
import csv
import json
import re
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from trendline_scanner_v25_live_schwab import (
    get_schwab_client,
    fetch_schwab_quotes,
    is_us_regular_market_open,
    touch_both_schwab_tokens,
)

DATA_DIR = Path("/data/tapes")
SAVE_TAPES = True
MAX_TAPE_MB = 50
MAX_TAPE_ROWS = 900000

# Overall tape retention limits.
MAX_TOTAL_TAPE_MB = 250
MAX_TAPE_FILES = 10
MAINTENANCE_SECONDS = 60

LOCAL_DATA_DIR = Path("data/tapes")
POLL_SECONDS = 1
TOKEN_TOUCH_SECONDS = 600
ELIGIBILITY_STATUS_PATH = Path("/data/eligibility_status.json")
ELIGIBILITY_REFRESH_SCRIPT = Path("/app/refresh_eligible_symbols.py")

def tape_path():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    base = DATA_DIR if Path("/data").exists() else LOCAL_DATA_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"quotes_{today}.csv"

def _write_eligibility_status(cache_path, symbol_count, used_fallback):
    """Atomically record the exact eligibility universe used by the collector."""
    now = datetime.now(timezone.utc)
    match = re.search(r"eligible_symbols_(\d{8})\.csv$", cache_path.name)
    cache_date = None
    age_days = None

    if match:
        try:
            parsed = datetime.strptime(match.group(1), "%Y%m%d").date()
            cache_date = parsed.isoformat()
            age_days = (now.date() - parsed).days
        except ValueError:
            pass

    current = not used_fallback and age_days == 0
    payload = {
        "filename": cache_path.name,
        "path": str(cache_path),
        "cache_date": cache_date,
        "symbol_count": int(symbol_count),
        "used_fallback": bool(used_fallback),
        "age_days": age_days,
        "loaded_at": now.isoformat(),
        "status": "CURRENT" if current else "STALE",
    }

    ELIGIBILITY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ELIGIBILITY_STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(ELIGIBILITY_STATUS_PATH)


def refresh_eligibility_cache():
    """Run the one-shot builder. Used at UTC date rollover while markets are closed."""
    if not ELIGIBILITY_REFRESH_SCRIPT.exists():
        print(f"[warn] eligibility refresh script missing: {ELIGIBILITY_REFRESH_SCRIPT}", flush=True)
        return False
    try:
        completed = subprocess.run(
            [os.sys.executable, "-u", str(ELIGIBILITY_REFRESH_SCRIPT)],
            cwd="/app",
            env=os.environ.copy(),
            check=False,
        )
        if completed.returncode != 0:
            print(f"[warn] eligibility refresh exited {completed.returncode}", flush=True)
            return False
        return True
    except Exception as exc:
        print(f"[warn] eligibility refresh failed: {type(exc).__name__}: {exc}", flush=True)
        return False


def load_symbols():
    # Prefer today's eligible cache on Fly, but visibly record any fallback.
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    preferred = [
        Path("/data") / f"eligible_symbols_{today}.csv",
        Path(f"eligible_symbols_{today}.csv"),
        Path("/app") / f"eligible_symbols_{today}.csv",
    ]

    p = next((x for x in preferred if x.exists() and x.stat().st_size > 0), None)
    used_fallback = False

    if p is None:
        candidates = []
        for base in [Path("/data"), Path("/app"), Path(".")]:
            candidates.extend(base.glob("eligible_symbols_*.csv"))

        candidates = sorted(
            [x for x in candidates if x.exists() and x.stat().st_size > 0],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        if not candidates:
            raise FileNotFoundError(
                "No eligible cache found for today and no fallback eligible_symbols_*.csv found"
            )

        p = candidates[0]
        used_fallback = True
        print(f"[warn] today's eligible cache missing; using fallback: {p}", flush=True)

    import pandas as pd
    cached = pd.read_csv(p)
    if "symbol" not in cached.columns:
        raise RuntimeError(f"Eligibility cache has no symbol column: {p}")

    symbols = cached["symbol"].dropna().astype(str).str.strip().tolist()
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        raise RuntimeError(f"Eligibility cache contains zero symbols: {p}")

    _write_eligibility_status(p, len(symbols), used_fallback)
    return symbols


def trim_all_existing_tapes():
    tape_dir = Path("/data/tapes")
    if not tape_dir.exists():
        return
    for path in sorted(tape_dir.glob("quotes_*.csv")):
        try:
            trim_tape_file(path)
        except Exception as e:
            print(f"trim existing tape error {path}: {type(e).__name__}: {e}", flush=True)

def trim_tape_file(path):
    try:
        if not path.exists():
            return
        max_bytes = MAX_TAPE_MB * 1024 * 1024
        if path.stat().st_size <= max_bytes:
            return

        # Do not read the whole tape into Python.  The previous implementation
        # held several copies of a 25MB CSV (str, list[str], body, tail, join),
        # which created large transient RSS spikes and could trigger the OOM
        # killer.  Let coreutils stream the tail into temporary files instead.
        header = b"timestamp_utc,symbol,last_price\n"
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as rows_tmp:
            rows_tmp_path = Path(rows_tmp.name)
            subprocess.run(
                ["tail", "-n", str(MAX_TAPE_ROWS), str(path)],
                stdout=rows_tmp,
                stderr=subprocess.PIPE,
                check=True,
            )

        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as final_tmp:
            final_tmp_path = Path(final_tmp.name)
            final_tmp.write(header)
            payload_limit = max(1, max_bytes - len(header))

            with rows_tmp_path.open("rb") as src:
                if rows_tmp_path.stat().st_size > payload_limit:
                    src.seek(-payload_limit, os.SEEK_END)
                    src.readline()  # discard a possibly partial CSV row

                first = src.readline()
                if first and not first.startswith(b"timestamp_utc,"):
                    final_tmp.write(first)
                shutil.copyfileobj(src, final_tmp, length=1024 * 1024)

        os.replace(final_tmp_path, path)
        rows_tmp_path.unlink(missing_ok=True)
        print(
            f"trimmed tape {path} to {path.stat().st_size/1024/1024:.1f}MB",
            flush=True,
        )
    except Exception as e:
        print(f"trim_tape_file_error {path}: {e}", flush=True)
        for tmp_name in (locals().get("rows_tmp_path"), locals().get("final_tmp_path")):
            if tmp_name is not None:
                Path(tmp_name).unlink(missing_ok=True)



def prune_old_tapes(active_path=None):
    """Delete oldest completed tapes when storage limits are exceeded."""
    tape_dir = DATA_DIR if Path("/data").exists() else LOCAL_DATA_DIR
    if not tape_dir.exists():
        return

    active_resolved = active_path.resolve() if active_path is not None else None

    files = sorted(
        [path for path in tape_dir.glob("quotes_*.csv") if path.exists()],
        key=lambda path: (path.name, path.stat().st_mtime),
    )

    max_total_bytes = MAX_TOTAL_TAPE_MB * 1024 * 1024

    def total_bytes():
        return sum(path.stat().st_size for path in files if path.exists())

    while len(files) > MAX_TAPE_FILES or total_bytes() > max_total_bytes:
        removable = [
            path for path in files
            if active_resolved is None or path.resolve() != active_resolved
        ]

        if not removable:
            print(
                "tape retention warning: limits exceeded but only active tape remains",
                flush=True,
            )
            break

        oldest = removable[0]

        try:
            size_mb = oldest.stat().st_size / 1024 / 1024
            oldest.unlink()
            files.remove(oldest)
            print(
                f"deleted old tape {oldest} size={size_mb:.1f}MB "
                f"remaining_files={len(files)}",
                flush=True,
            )
        except Exception as e:
            print(
                f"delete old tape error {oldest}: {type(e).__name__}: {e}",
                flush=True,
            )
            break



def append_quotes(path, timestamp, prices):
    new_file = not path.exists()
    if not SAVE_TAPES:
        return

    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp_utc", "symbol", "last_price"])
        for sym, px in prices.items():
            w.writerow([timestamp, sym, px])

def main():
    trim_all_existing_tapes()
    print("live_quote_collector.py starting", flush=True)
    symbols = load_symbols()
    print(f"Loaded {len(symbols)} symbols", flush=True)

    client = get_schwab_client()
    print("Connected to Schwab", flush=True)

    # Immediately touch both Schwab tokens on collector startup,
    # then repeat every TOKEN_TOUCH_SECONDS.
    touch_both_schwab_tokens()
    last_token_touch = time.time()

    path = tape_path()
    print(f"Writing tape to {path}", flush=True)

    prune_old_tapes(active_path=path)
    last_maintenance = time.time()

    cycle = 0
    while True:
        cycle += 1
        start = time.perf_counter()

        # Recalculate the UTC-dated tape path every cycle.
        current_path = tape_path()

        if current_path != path:
            old_path = path
            path = current_path

            # Build and reload the new UTC day's eligibility universe.
            refresh_eligibility_cache()
            symbols = load_symbols()

            print(
                f"Rolled tape from {old_path} to {path}; "
                f"loaded {len(symbols)} symbols",
                flush=True,
            )

            trim_tape_file(old_path)
            prune_old_tapes(active_path=path)
            last_maintenance = time.time()

        if time.time() - last_token_touch > TOKEN_TOUCH_SECONDS:
            touch_both_schwab_tokens()
            last_token_touch = time.time()

        # Run expensive tape maintenance periodically, not after every write.
        if time.time() - last_maintenance > MAINTENANCE_SECONDS:
            trim_tape_file(path)
            prune_old_tapes(active_path=path)
            last_maintenance = time.time()

        ts = datetime.now(timezone.utc).isoformat()

        prices = fetch_schwab_quotes(client, symbols)
        append_quotes(path, ts, prices)

        elapsed = time.perf_counter() - start
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"collector cycle {cycle} | quotes={len(prices)}/{len(symbols)} | "
            f"elapsed={elapsed:.2f}s | file={path}",
            flush=True,
        )

        time.sleep(max(0, POLL_SECONDS - elapsed))

    

if __name__ == "__main__":
    main()
