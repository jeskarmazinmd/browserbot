from abc import ABC, abstractmethod


class QuoteSource(ABC):
    @abstractmethod
    def read_data(self):
        raise NotImplementedError


class LiveQuoteSource(QuoteSource):
    def __init__(self, reader=None):
        self._reader = reader

    def read_data(self):
        if self._reader is not None:
            return self._reader()
        return read_data()

    def now(self):
        return datetime.now(timezone.utc)


# Auto-generated from live_strategy_runner.py

from pathlib import Path
from datetime import datetime, timezone
import os
import time
import pandas as pd

# Globals

_TAPE_CACHE = None
_TAPE_OFFSET = 0
_TAPE_PARTIAL = b""
_TAPE_PATH = None
_TAPE_INODE = None
CACHE_MINUTES = 75
INITIAL_TAIL_ROWS = 900_000
MINUTE_CACHE_SAVE_SECONDS = 60
_LAST_MINUTE_CACHE_SAVE = 0.0

# Functions

def _parse_quote_bytes(payload):
    """Parse complete raw CSV rows from an in-memory byte payload."""
    import io

    if not payload:
        return pd.DataFrame(columns=["timestamp", "symbol", "price"])

    df = pd.read_csv(
        io.BytesIO(payload),
        names=["timestamp", "symbol", "price"],
        dtype={"symbol": "string"},
        low_memory=False,
    )

    df = df[df["timestamp"] != "timestamp_utc"]
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        format="ISO8601",
        errors="coerce",
        utc=True,
    )
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    return df.dropna(subset=["timestamp", "symbol", "price"])

def _to_minute_cache(df):
    """Collapse raw quotes to the final quote for each symbol/clock minute."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "price"])

    work = df.sort_values("timestamp").copy()
    work["timestamp"] = work["timestamp"].dt.floor("min")

    return (
        work.groupby(["symbol", "timestamp"], as_index=False, sort=False)["price"]
        .last()
        [["timestamp", "symbol", "price"]]
        .sort_values(["timestamp", "symbol"])
        .reset_index(drop=True)
    )

def _merge_minute_cache(current, incoming):
    if incoming is None or incoming.empty:
        return current

    if current is None or current.empty:
        merged = incoming.copy()
    else:
        merged = pd.concat([current, incoming], ignore_index=True)

    merged = (
        merged.sort_values(["timestamp", "symbol"])
        .drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    )

    newest = merged["timestamp"].max()
    if pd.notna(newest):
        cutoff = newest - pd.Timedelta(minutes=CACHE_MINUTES)
        merged = merged[merged["timestamp"] >= cutoff]

    return merged.reset_index(drop=True)

def _persistent_minute_cache_path(tape):
    data_root = tape.parent.parent if tape.parent.name == "tapes" else tape.parent
    market_day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return data_root / f"minute_quote_cache_{market_day}.pkl"

def _load_persistent_minute_cache(tape):
    path = _persistent_minute_cache_path(tape)
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        cached = pd.read_pickle(path)
        required = {"timestamp", "symbol", "price"}
        if not isinstance(cached, pd.DataFrame) or not required.issubset(cached.columns):
            raise ValueError("unexpected minute-cache schema")
        cached = cached[["timestamp", "symbol", "price"]].copy()
        cached["timestamp"] = pd.to_datetime(cached["timestamp"], errors="coerce", utc=True)
        cached["price"] = pd.to_numeric(cached["price"], errors="coerce")
        cached = cached.dropna(subset=["timestamp", "symbol", "price"])
        print(
            f"PERSISTENT_MINUTE_CACHE_LOADED rows={len(cached)} path={path}",
            flush=True,
        )
        return cached
    except Exception as exc:
        print(f"persistent minute cache load error: {type(exc).__name__}: {exc}", flush=True)
        return None

def _save_persistent_minute_cache(tape, cache, force=False):
    global _LAST_MINUTE_CACHE_SAVE
    if cache is None or cache.empty:
        return False
    now = time.monotonic()
    if not force and now - _LAST_MINUTE_CACHE_SAVE < MINUTE_CACHE_SAVE_SECONDS:
        return False
    path = _persistent_minute_cache_path(tape)
    temporary = path.with_name(path.name + ".tmp")
    try:
        cache.to_pickle(temporary)
        os.replace(temporary, path)
        _LAST_MINUTE_CACHE_SAVE = now
        return True
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        print(f"persistent minute cache save error: {type(exc).__name__}: {exc}", flush=True)
        return False

def _initialise_tape_cache(tape):
    """Load restart history once, then remember the current byte position."""
    global _TAPE_CACHE, _TAPE_PATH, _TAPE_OFFSET, _TAPE_INODE, _TAPE_PARTIAL

    import subprocess
    import tempfile

    stat_before = tape.stat()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            subprocess.run(
                ["tail", "-n", str(INITIAL_TAIL_ROWS), str(tape)],
                stdout=tmp,
                stderr=subprocess.DEVNULL,
                check=True,
            )

        payload = tmp_path.read_bytes()
        raw = _parse_quote_bytes(payload)
        tail_minutes = _to_minute_cache(raw)
        persisted = _load_persistent_minute_cache(tape)
        _TAPE_CACHE = _merge_minute_cache(persisted, tail_minutes)

        _TAPE_PATH = tape
        _TAPE_OFFSET = stat_before.st_size
        _TAPE_INODE = stat_before.st_ino
        _TAPE_PARTIAL = b""

        print(
            "TAPE_CACHE_INITIALIZED "
            f"raw_rows={len(raw)} minute_rows={len(_TAPE_CACHE)} "
            f"offset={_TAPE_OFFSET}",
            flush=True,
        )
        _save_persistent_minute_cache(tape, _TAPE_CACHE, force=True)
        return _TAPE_CACHE

    except Exception as e:
        print(
            f"tape cache initialization error: {type(e).__name__}: {e}",
            flush=True,
        )
        return None

    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

def read_data():
    """Return a rolling minute-level cache, reading only newly appended rows."""
    global _TAPE_CACHE, _TAPE_PATH, _TAPE_OFFSET, _TAPE_INODE, _TAPE_PARTIAL

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = [
        Path("/data/tapes") / f"quotes_{today}.csv",
        Path(f"quotes_{today}.csv"),
    ]

    tape = next(
        (x for x in candidates if x.exists() and x.stat().st_size > 0),
        None,
    )
    if tape is None:
        return None

    try:
        stat_now = tape.stat()

        # First run, a new trading day, or collector trim via os.replace.
        if (
            _TAPE_CACHE is None
            or _TAPE_PATH != tape
            or _TAPE_INODE != stat_now.st_ino
            or stat_now.st_size < _TAPE_OFFSET
        ):
            return _initialise_tape_cache(tape)

        if stat_now.st_size == _TAPE_OFFSET:
            return _TAPE_CACHE

        with tape.open("rb") as source:
            source.seek(_TAPE_OFFSET)
            chunk = source.read()
            new_offset = source.tell()

        payload = _TAPE_PARTIAL + chunk

        # Parse only complete CSV lines. Preserve a partial final write.
        if payload.endswith(b"\n"):
            complete = payload
            _TAPE_PARTIAL = b""
        else:
            complete, separator, remainder = payload.rpartition(b"\n")
            if not separator:
                _TAPE_PARTIAL = payload
                _TAPE_OFFSET = new_offset
                return _TAPE_CACHE
            complete += b"\n"
            _TAPE_PARTIAL = remainder

        _TAPE_OFFSET = new_offset

        raw_new = _parse_quote_bytes(complete)
        minute_new = _to_minute_cache(raw_new)
        _TAPE_CACHE = _merge_minute_cache(_TAPE_CACHE, minute_new)
        _save_persistent_minute_cache(tape, _TAPE_CACHE)

        return _TAPE_CACHE

    except Exception as e:
        print(f"incremental tape read error: {type(e).__name__}: {e}", flush=True)
        return _TAPE_CACHE
