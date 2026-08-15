"""Dedicated C3N25S10 execution-path validator. No broker order code."""
from __future__ import annotations

import json, math, os, threading, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from live_strategy_runner import detect_latest_flash, measure_latest_flash
from strategies import strategy_c3n25s10 as strategy
from trendline_scanner_v25_live_schwab import (
    fetch_schwab_quote_snapshots, load_symbols,
)

ROOT = Path("/data")
LEDGER = ROOT / "c3_live_shadow.jsonl"
STATUS = ROOT / "c3_live_status.json"
STATE = ROOT / "c3_live_state.json"
NY = ZoneInfo("America/New_York")

UNIVERSE_SECONDS = float(os.getenv("C3_UNIVERSE_SECONDS", "5"))
PRIORITY_SECONDS = float(os.getenv("C3_PRIORITY_SECONDS", "0.5"))
ORDER_LATENCY_MS = int(os.getenv("C3_ORDER_LATENCY_MS", "250"))
MAX_QUOTE_AGE_MS = int(os.getenv("C3_MAX_QUOTE_AGE_MS", "2500"))
MAX_SPREAD_PCT = float(os.getenv("C3_MAX_SPREAD_PCT", "0.25"))
ENTRY_LIMIT_BPS = float(os.getenv("C3_ENTRY_LIMIT_BPS", "5"))
STRESS_BPS = float(os.getenv("C3_STRESS_BPS", "5"))
STARTING_CASH = float(os.getenv("C3_STARTING_CASH", "5000"))
SLOT_NOTIONAL = float(os.getenv("C3_SLOT_NOTIONAL", "1000"))
TOKEN_LEASE_URL = os.getenv(
    "MARKET_TOKEN_LEASE_URL",
    "http://schwab.internal:8081/internal/market-access-token",
)
TOKEN_LEASE_SECRET = os.getenv("MARKET_TOKEN_LEASE_SECRET", "")
SCHWAB_QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"

lock = threading.RLock()
bars = defaultdict(dict)
pending, entry_orders, positions, seen = {}, {}, {}, set()
cash = STARTING_CASH
counters = defaultdict(int)
metrics = {"universe_fetch_seconds": None, "priority_fetch_seconds": None}


class LeasedMarketDataClient:
    """Quote client holding only a short-lived access token in memory."""

    def __init__(self):
        if not TOKEN_LEASE_SECRET:
            raise RuntimeError("MARKET_TOKEN_LEASE_SECRET is required")
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._access_token = ""
        self._expires_at = 0.0

    def _lease(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._access_token and self._expires_at > time.time() + 30:
                return self._access_token
            response = self._session.get(
                TOKEN_LEASE_URL,
                headers={"X-Token-Lease-Secret": TOKEN_LEASE_SECRET},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            self._access_token = str(payload["access_token"])
            self._expires_at = float(payload["expires_at"])
            counters["token_leases"] += 1
            return self._access_token

    def _request_quotes(self, symbols, token):
        return self._session.get(
            SCHWAB_QUOTES_URL,
            params={"symbols": ",".join(symbols)},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )

    def get_quotes(self, symbols):
        response = self._request_quotes(symbols, self._lease())
        if response.status_code == 401:
            response = self._request_quotes(symbols, self._lease(force=True))
        return response


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, separators=(",", ":"), default=str))
    os.replace(tmp, path)


def emit(event, **fields):
    row = {"event": event, "recorded_at": datetime.now(timezone.utc).isoformat(), **fields}
    with LEDGER.open("a") as f:
        f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    return row


def px(snapshot):
    return snapshot.last or snapshot.legacy_price


def quote_ok(snapshot, now):
    if not snapshot or not snapshot.bid or not snapshot.ask or snapshot.ask < snapshot.bid:
        return False, "missing_or_crossed_quote"
    if snapshot.realtime is False:
        return False, "not_realtime"
    if snapshot.quote_time_ms:
        age = now.timestamp() * 1000 - snapshot.quote_time_ms
        if age > MAX_QUOTE_AGE_MS:
            return False, "stale_quote"
    spread = (snapshot.ask / snapshot.bid - 1) * 100
    if spread > MAX_SPREAD_PCT:
        return False, "spread_too_wide"
    return True, None


def market_open(now):
    et = now.astimezone(NY)
    return et.weekday() < 5 and (9, 30) <= (et.hour, et.minute) < (16, 0)


def entry_open(now):
    et = now.astimezone(NY)
    return market_open(now) and (et.hour, et.minute) < (15, 30)


def at_eod(now):
    et = now.astimezone(NY)
    return et.weekday() < 5 and (et.hour, et.minute) >= (15, 55)


def series_for(symbol):
    values = bars[symbol]
    if not values:
        return pd.Series(dtype=float)
    s = pd.Series(values).sort_index()
    s.index = pd.DatetimeIndex(s.index)
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="1min"))


def detect(symbol, snapshot, now):
    price = px(snapshot)
    if not price or not entry_open(now) or symbol in pending or symbol in entry_orders or symbol in positions:
        return
    minute = pd.Timestamp(now).floor("min")
    values = bars[symbol]
    values[minute] = float(price)
    cutoff = minute - pd.Timedelta(minutes=40)
    for key in list(values):
        if key < cutoff:
            del values[key]
    s = series_for(symbol)
    measurement = measure_latest_flash(symbol, None, prices=s)
    event = detect_latest_flash(symbol, None, measurement=measurement) if measurement else None
    if not event or not strategy.accepts_flash(event, 12.0):
        return
    key = f"{symbol}|{event['signal_window_end']}"
    if key in seen:
        return
    seen.add(key)
    pending[symbol] = {"key": key, "created_at": now, "lowest": float(price), "event": event}
    counters["signals"] += 1
    emit("SIGNAL", strategy_id=strategy.STRATEGY_ID, symbol=symbol, setup_id=key, signal=event)


def update_pending(symbol, snapshot, now):
    p = pending.get(symbol)
    price = px(snapshot)
    if not p or not price:
        return
    p["lowest"] = min(p["lowest"], float(price))
    age = (now - p["created_at"]).total_seconds()
    if age >= 600:
        emit("ENTRY_REJECT", symbol=symbol, setup_id=p["key"], reason="rebound_timeout")
        pending.pop(symbol, None); counters["entry_rejects"] += 1; return
    if float(price) / p["lowest"] - 1 < strategy.CONFIG["rebound_confirmation_pct"]:
        return
    ok, reason = quote_ok(snapshot, now)
    if not ok:
        emit("ENTRY_REJECT", symbol=symbol, setup_id=p["key"], reason=reason)
        pending.pop(symbol, None); counters["entry_rejects"] += 1; return
    event = strategy.refresh_event_for_entry(p["event"], float(price))
    remaining = (float(event["target_price"]) / float(snapshot.ask) - 1) * 100
    if remaining < 0.20:
        emit("ENTRY_REJECT", symbol=symbol, setup_id=p["key"], reason="insufficient_ask_based_upside", remaining_upside_pct=remaining)
        pending.pop(symbol, None); counters["entry_rejects"] += 1; return
    entry_orders[symbol] = {
        "key": p["key"], "decision_at": now, "due_at": now.timestamp() + ORDER_LATENCY_MS / 1000,
        "expires_at": now.timestamp() + 2, "limit": float(snapshot.ask) * (1 + ENTRY_LIMIT_BPS / 10000),
        "signal_price": float(price), "target": float(event["target_price"]), "event": event,
    }
    pending.pop(symbol, None)
    emit("ENTRY_DECISION", symbol=symbol, setup_id=p["key"], ask=snapshot.ask, bid=snapshot.bid, limit=entry_orders[symbol]["limit"])


def update_entry_order(symbol, snapshot, now):
    global cash
    order = entry_orders.get(symbol)
    if not order or now.timestamp() < order["due_at"]:
        return
    ok, reason = quote_ok(snapshot, now)
    if not ok or not snapshot.ask or snapshot.ask > order["limit"]:
        if now.timestamp() >= order["expires_at"]:
            emit("ENTRY_REJECT", symbol=symbol, setup_id=order["key"], reason=reason or "limit_not_filled")
            entry_orders.pop(symbol, None); counters["entry_rejects"] += 1
        return
    fill = float(snapshot.ask)
    budget = min(SLOT_NOTIONAL, cash)
    shares = math.floor(budget / fill)
    if shares < 1:
        emit("ENTRY_REJECT", symbol=symbol, setup_id=order["key"], reason="insufficient_cash")
        entry_orders.pop(symbol, None); counters["entry_rejects"] += 1; return
    cost = shares * fill; cash -= cost
    price = float(px(snapshot) or fill)
    positions[symbol] = {
        "key": order["key"], "entry_at": now, "entry_fill": fill, "stress_entry": fill * (1 + STRESS_BPS / 10000),
        "shares": shares, "cost": cost, "target": order["target"], "stop": fill * 0.99,
        "highest": price, "highest_at": now, "activated": False, "exit_due_at": None, "exit_reason": None,
    }
    entry_orders.pop(symbol, None); counters["entries"] += 1
    emit("ENTRY_FILL", strategy_id=strategy.STRATEGY_ID, symbol=symbol, **positions[symbol], bid=snapshot.bid, ask=snapshot.ask, cash=cash)


def close_position(symbol, snapshot, now, reason, fill):
    global cash
    p = positions.pop(symbol)
    fill = float(fill); proceeds = p["shares"] * fill; cash += proceeds
    stress_exit = fill * (1 - STRESS_BPS / 10000)
    pnl = (fill - p["entry_fill"]) * p["shares"]
    stress_pnl = (stress_exit - p["stress_entry"]) * p["shares"]
    counters["exits"] += 1
    emit("EXIT_FILL", strategy_id=strategy.STRATEGY_ID, symbol=symbol, setup_id=p["key"], reason=reason,
         exit_at=now, exit_fill=fill, stress_exit_fill=stress_exit, bid=snapshot.bid, ask=snapshot.ask,
         pnl=pnl, stress_pnl=stress_pnl, return_pct=(fill / p["entry_fill"] - 1) * 100,
         stress_return_pct=(stress_exit / p["stress_entry"] - 1) * 100, shares=p["shares"], cash=cash)


def update_position(symbol, snapshot, now):
    p = positions.get(symbol); price = px(snapshot)
    if not p or not price or not snapshot.bid:
        return
    price = float(price)
    if p["exit_due_at"] is not None and now.timestamp() >= p["exit_due_at"]:
        close_position(symbol, snapshot, now, p["exit_reason"], snapshot.bid); return
    if price <= p["stop"]:
        close_position(symbol, snapshot, now, "STOP", snapshot.bid); return
    if at_eod(now):
        close_position(symbol, snapshot, now, "EOD", snapshot.bid); return
    if price > p["highest"]:
        p["highest"], p["highest_at"] = price, now
    if not p["activated"] and price >= p["entry_fill"] * 1.003:
        p["activated"] = True; p["highest_at"] = now
        emit("ACTIVATED", symbol=symbol, setup_id=p["key"], price=price)
    if p["activated"] and (now - p["highest_at"]).total_seconds() >= 30:
        p["exit_reason"] = "NO_NEW_HIGH"
        p["exit_due_at"] = now.timestamp() + ORDER_LATENCY_MS / 1000
        emit("EXIT_DECISION", symbol=symbol, setup_id=p["key"], reason="NO_NEW_HIGH", bid=snapshot.bid, ask=snapshot.ask)


def write_status():
    with lock:
        atomic_json(STATUS, {"updated_at": datetime.now(timezone.utc), "strategy_id": strategy.STRATEGY_ID,
            "mode": "SHADOW", "live_order_placement_enabled": False, "cash": cash,
            "pending": len(pending), "entry_orders": len(entry_orders), "positions": len(positions),
            "counters": dict(counters), "metrics": metrics})


def universe_loop(client, symbols):
    while True:
        started = time.perf_counter(); now = datetime.now(timezone.utc)
        try:
            snapshots = fetch_schwab_quote_snapshots(client, symbols)
            with lock:
                for symbol, snapshot in snapshots.items(): detect(symbol, snapshot, now)
            counters["universe_cycles"] += 1
        except Exception as exc:
            counters["errors"] += 1; emit("ERROR", worker="universe", error=repr(exc))
        metrics["universe_fetch_seconds"] = time.perf_counter() - started
        write_status(); time.sleep(max(0.05, UNIVERSE_SECONDS - (time.perf_counter() - started)))


def priority_loop(client):
    while True:
        with lock: symbols = sorted(set(pending) | set(entry_orders) | set(positions))
        if not symbols:
            write_status(); time.sleep(PRIORITY_SECONDS); continue
        started = time.perf_counter(); now = datetime.now(timezone.utc)
        try:
            snapshots = fetch_schwab_quote_snapshots(client, symbols)
            with lock:
                for symbol, snapshot in snapshots.items():
                    update_pending(symbol, snapshot, now)
                    update_entry_order(symbol, snapshot, now)
                    update_position(symbol, snapshot, now)
            counters["priority_cycles"] += 1
        except Exception as exc:
            counters["errors"] += 1; emit("ERROR", worker="priority", error=repr(exc))
        metrics["priority_fetch_seconds"] = time.perf_counter() - started
        write_status(); time.sleep(max(0.05, PRIORITY_SECONDS - (time.perf_counter() - started)))


def main():
    if os.getenv("LIVE_ORDER_PLACEMENT_ENABLED", "0").strip() != "0":
        raise RuntimeError("c3 live validation build refuses real-order enablement")
    ROOT.mkdir(parents=True, exist_ok=True)
    client = None
    while client is None:
        atomic_json(STATUS, {
            "updated_at": datetime.now(timezone.utc),
            "strategy_id": strategy.STRATEGY_ID,
            "mode": "WAITING_FOR_MARKET_TOKEN_LEASE",
            "live_order_placement_enabled": False,
        })
        try:
            client = LeasedMarketDataClient()
            client._lease()
        except Exception as exc:
            client = None
            emit("TOKEN_LEASE_WAIT", error=repr(exc))
            time.sleep(10)
    symbols = [s for s in load_symbols() if s not in {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}]
    emit("START", strategy_id=strategy.STRATEGY_ID, symbols=len(symbols), mode="SHADOW")
    threading.Thread(target=universe_loop, args=(client, symbols), daemon=True).start()
    priority_loop(client)


if __name__ == "__main__":
    main()
