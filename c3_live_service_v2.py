"""Dedicated, durable C3N25S10 executable-price shadow service.

This build deliberately contains no broker-order implementation. It validates
the exact state machine and fill assumptions that a later broker adapter uses.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from c3_live_logic import C3Config
from c3_live_runtime import DurableC3, snapshot_quote
from live_strategy_runner import detect_latest_flash, measure_latest_flash
from strategies import strategy_c3n25s10 as strategy
from trendline_scanner_v25_live_schwab import fetch_schwab_quote_snapshots, load_symbols

ROOT = Path("/data")
STATE = ROOT / "c3_live_state_v2.json"
LEDGER = ROOT / "c3_live_shadow_v2.jsonl"
OPS = ROOT / "c3_live_operations_v2.jsonl"
STATUS = ROOT / "c3_live_status.json"
BAR_STATE = ROOT / "c3_live_bars_v2.json"
NY = ZoneInfo("America/New_York")

UNIVERSE_SECONDS = float(os.getenv("C3_UNIVERSE_SECONDS", "5"))
PRIORITY_SECONDS = float(os.getenv("C3_PRIORITY_SECONDS", "0.5"))
TOKEN_LEASE_URL = os.getenv(
    "MARKET_TOKEN_LEASE_URL", "http://schwab.internal:8081/internal/market-access-token"
)
TOKEN_LEASE_SECRET = os.getenv("MARKET_TOKEN_LEASE_SECRET", "")
SCHWAB_QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"

CONFIG = C3Config(
    rebound_fraction=float(strategy.CONFIG["rebound_confirmation_pct"]),
    stop_fraction=float(strategy.CONFIG["stop_loss_fraction"]),
    activation_fraction=float(strategy.CONFIG["activation_gain_pct"]) / 100.0,
    no_new_high_seconds=float(strategy.CONFIG["no_new_high_seconds"]),
    order_latency_seconds=float(os.getenv("C3_ORDER_LATENCY_MS", "250")) / 1000.0,
    max_quote_age_seconds=float(os.getenv("C3_MAX_QUOTE_AGE_MS", "2500")) / 1000.0,
    max_spread_pct=float(os.getenv("C3_MAX_SPREAD_PCT", "0.25")),
    entry_limit_bps=float(os.getenv("C3_ENTRY_LIMIT_BPS", "5")),
    stress_bps=float(os.getenv("C3_STRESS_BPS", "5")),
    starting_cash=float(os.getenv("C3_STARTING_CASH", "5000")),
    slot_notional=float(os.getenv("C3_SLOT_NOTIONAL", "1000")),
)

service_lock = threading.RLock()
bars: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)
counters: dict[str, int] = defaultdict(int)
metrics = {"universe_fetch_seconds": None, "priority_fetch_seconds": None}
runtime: DurableC3 | None = None
last_bar_save = 0.0


class LeasedMarketDataClient:
    def __init__(self):
        if not TOKEN_LEASE_SECRET:
            raise RuntimeError("MARKET_TOKEN_LEASE_SECRET is required")
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.access_token = ""
        self.expires_at = 0.0

    def lease(self, force=False):
        with self.lock:
            if not force and self.access_token and self.expires_at > time.time() + 30:
                return self.access_token
            response = self.session.get(
                TOKEN_LEASE_URL,
                headers={"X-Token-Lease-Secret": TOKEN_LEASE_SECRET},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            self.access_token = str(payload["access_token"])
            self.expires_at = float(payload["expires_at"])
            counters["token_leases"] += 1
            return self.access_token

    def get_quotes(self, symbols):
        def request(token):
            return self.session.get(
                SCHWAB_QUOTES_URL,
                params={"symbols": ",".join(symbols)},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10,
            )
        response = request(self.lease())
        return request(self.lease(force=True)) if response.status_code == 401 else response


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, separators=(",", ":"), default=str, allow_nan=False))
    os.replace(tmp, path)


def op(event, **fields):
    row = {"event": event, "recorded_at": datetime.now(timezone.utc).isoformat(), **fields}
    with OPS.open("a") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")


def market_open(now):
    et = now.astimezone(NY)
    return et.weekday() < 5 and (9, 30) <= (et.hour, et.minute) < (16, 0)


def entry_open(now):
    et = now.astimezone(NY)
    return market_open(now) and (et.hour, et.minute) < (15, 30)


def at_eod(now):
    et = now.astimezone(NY)
    return et.weekday() < 5 and (et.hour, et.minute) >= (15, 55)


def load_bars():
    if not BAR_STATE.exists():
        return
    payload = json.loads(BAR_STATE.read_text())
    for symbol, values in payload.items():
        bars[symbol] = {pd.Timestamp(float(ts), unit="s", tz="UTC"): float(px)
                        for ts, px in values}


def save_bars(force=False):
    global last_bar_save
    now = time.time()
    if not force and now - last_bar_save < 60:
        return
    payload = {symbol: [[stamp.timestamp(), price] for stamp, price in values.items()]
               for symbol, values in bars.items() if values}
    atomic_json(BAR_STATE, payload)
    last_bar_save = now


def series_for(symbol):
    values = bars[symbol]
    if not values:
        return pd.Series(dtype=float)
    series = pd.Series(values).sort_index()
    series.index = pd.DatetimeIndex(series.index)
    return series.reindex(pd.date_range(series.index.min(), series.index.max(), freq="1min"))


def account_events(events):
    for row in events:
        mapping = {
            "SIGNAL": "signals", "ENTRY_REJECT": "entry_rejects",
            "ENTRY_FILL": "entries", "EXIT_FILL": "exits",
            "ENTRY_GATE_BLOCK": "entry_gate_blocks",
            "POSITION_QUOTE_BLOCK": "position_quote_blocks",
        }
        if row["event"] in mapping:
            counters[mapping[row["event"]]] += 1


def detect(symbol, snapshot, received_at):
    assert runtime is not None
    price = snapshot.last or snapshot.mark
    now = datetime.fromtimestamp(received_at, timezone.utc)
    if not price or not entry_open(now):
        return
    minute = pd.Timestamp(now).floor("min")
    values = bars[symbol]
    values[minute] = float(price)
    cutoff = minute - pd.Timedelta(minutes=40)
    for stamp in list(values):
        if stamp < cutoff:
            del values[stamp]
    engine = runtime.engine
    if symbol in engine.pending or symbol in engine.orders or symbol in engine.positions:
        return
    series = series_for(symbol)
    measurement = measure_latest_flash(symbol, None, prices=series)
    event = detect_latest_flash(symbol, None, measurement=measurement) if measurement else None
    if not event or not strategy.accepts_flash(event, 12.0):
        return
    setup_id = f"{symbol}|{event['signal_window_end']}"
    quote = snapshot_quote(snapshot, received_at)
    events = runtime.register_signal(symbol, setup_id, float(event["target_price"]), quote)
    account_events(events)


def write_status():
    assert runtime is not None
    with service_lock, runtime.lock:
        engine = runtime.engine
        atomic_json(STATUS, {
            "updated_at": datetime.now(timezone.utc),
            "strategy_id": strategy.STRATEGY_ID,
            "mode": "SHADOW_V2",
            "live_order_placement_enabled": False,
            "cash": engine.cash,
            "pending": len(engine.pending),
            "entry_orders": len(engine.orders),
            "positions": len(engine.positions),
            "state_sequence": runtime.sequence,
            "counters": dict(counters),
            "metrics": metrics,
        })


def universe_loop(client, symbols):
    while True:
        started = time.perf_counter()
        try:
            snapshots = fetch_schwab_quote_snapshots(client, symbols)
            received_at = time.time()  # timestamp after the network response
            with service_lock:
                for symbol, snapshot in snapshots.items():
                    detect(symbol, snapshot, received_at)
                save_bars()
            counters["universe_cycles"] += 1
        except Exception as exc:
            counters["errors"] += 1
            op("ERROR", worker="universe", error=repr(exc))
        metrics["universe_fetch_seconds"] = time.perf_counter() - started
        write_status()
        time.sleep(max(0.05, UNIVERSE_SECONDS - (time.perf_counter() - started)))


def priority_loop(client):
    assert runtime is not None
    while True:
        with runtime.lock:
            engine = runtime.engine
            symbols = sorted(set(engine.pending) | set(engine.orders) | set(engine.positions))
        if not symbols:
            write_status()
            time.sleep(PRIORITY_SECONDS)
            continue
        started = time.perf_counter()
        try:
            snapshots = fetch_schwab_quote_snapshots(client, symbols)
            received_at = time.time()
            eod = at_eod(datetime.fromtimestamp(received_at, timezone.utc))
            for symbol, snapshot in snapshots.items():
                account_events(runtime.on_quote(snapshot_quote(snapshot, received_at), eod=eod))
            counters["priority_cycles"] += 1
        except Exception as exc:
            counters["errors"] += 1
            op("ERROR", worker="priority", error=repr(exc))
        metrics["priority_fetch_seconds"] = time.perf_counter() - started
        write_status()
        time.sleep(max(0.05, PRIORITY_SECONDS - (time.perf_counter() - started)))


def main():
    global runtime
    if os.getenv("LIVE_ORDER_PLACEMENT_ENABLED", "0").strip() != "0":
        raise RuntimeError("C3 shadow-v2 refuses real-order enablement")
    ROOT.mkdir(parents=True, exist_ok=True)
    load_bars()  # malformed recovery state intentionally prevents startup
    runtime = DurableC3.load(STATE, LEDGER, CONFIG)
    client = None
    while client is None:
        write_status()
        try:
            client = LeasedMarketDataClient()
            client.lease()
        except Exception as exc:
            client = None
            op("TOKEN_LEASE_WAIT", error=repr(exc))
            time.sleep(10)
    symbols = [s for s in load_symbols() if s not in {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}]
    op("START", strategy_id=strategy.STRATEGY_ID, symbols=len(symbols), mode="SHADOW_V2")
    threading.Thread(target=universe_loop, args=(client, symbols), daemon=True).start()
    priority_loop(client)


if __name__ == "__main__":
    main()
