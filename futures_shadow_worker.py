"""Isolated read-only Schwab micro-futures research worker."""
from __future__ import annotations

import gzip
import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from futures_paper_tracker import FuturesPaperTracker

ROOTS = ("/MES", "/MNQ", "/MGC", "/MCL", "/M6E")
STRATEGIES = (
    "FUTMES1", "FUTMNQ1", "FUTMESR1", "FUTMGCR1", "FUTMCLR1",
)
QUOTE_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
TOKEN_PATH = Path("/data/schwab_token.json")
DATA_ROOT = Path("/data")
POLL_SECONDS = int(os.getenv("FUTURES_SHADOW_POLL_SECONDS", "60"))
MAX_QUOTE_AGE_SECONDS = int(os.getenv("FUTURES_MAX_QUOTE_AGE_SECONDS", "180"))


def _token():
    obj = json.loads(TOKEN_PATH.read_text())
    return obj.get("token", obj)["access_token"]


def fetch_quotes(symbols):
    response = requests.get(QUOTE_URL, headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"}, params={"symbols": ",".join(symbols)}, timeout=20)
    response.raise_for_status()
    return response.json()


def normalize(symbol, payload):
    q = payload.get("quote") or {}
    ref = payload.get("reference") or {}
    return {
        "contractSymbol": symbol,
        "realtime": payload.get("realtime") is True,
        "bid": q.get("bidPrice"), "ask": q.get("askPrice"), "last": q.get("lastPrice"), "mark": q.get("mark"),
        "bidSize": q.get("bidSize"), "askSize": q.get("askSize"), "quoteTime": q.get("quoteTime"), "tradeTime": q.get("tradeTime"),
        "openInterest": q.get("openInterest"), "totalVolume": q.get("totalVolume"), "tick": q.get("tick"), "tickAmount": q.get("tickAmount"),
        "multiplier": ref.get("futureMultiplier"), "expiration": ref.get("futureExpirationDate"), "active": ref.get("futureIsActive"),
        "description": ref.get("description"), "exchange": ref.get("exchangeName"),
    }


def root_for(symbol):
    for root in sorted(ROOTS, key=len, reverse=True):
        if symbol == root or symbol.startswith(root):
            return root
    return None


def fresh(q, now):
    try:
        age = abs(now.timestamp() - float(q["quoteTime"]) / 1000)
        return q.get("realtime") is True and float(q["bid"]) > 0 and float(q["ask"]) >= float(q["bid"]) and float(q["multiplier"]) > 0 and age <= MAX_QUOTE_AGE_SECONDS
    except Exception:
        return False


def select_roots(normalized):
    chosen = {}
    for symbol, q in normalized.items():
        root = root_for(symbol)
        if not root:
            continue
        q = dict(q); q["root"] = root
        current = chosen.get(root)
        if current is None or (q.get("active") is True and current.get("active") is not True):
            chosen[root] = q
    return chosen


def archive(now, roots, exact):
    path = DATA_ROOT / "futures_tapes" / f"futures_quotes_{now:%Y%m%d}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at") as handle:
        handle.write(json.dumps({"timestamp": now.isoformat(), "roots": roots, "exact": exact}, separators=(",", ":")) + "\n")


def status(payload):
    path = DATA_ROOT / "futures_shadow_status.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(path)


def load_strategies():
    result = []
    for sid in STRATEGIES:
        module = importlib.import_module(f"futures_strategies.strategy_{sid.lower()}")
        assert module.PAPER_ONLY is True and module.LIVE_ORDER_PLACEMENT is False
        result.append(module.Strategy())
    return result


def main():
    tracker = FuturesPaperTracker(DATA_ROOT)
    strategies = load_strategies()
    errors = 0; decisions_count = 0
    while True:
        started = time.monotonic(); now = datetime.now(timezone.utc)
        try:
            requested = list(ROOTS) + tracker.required_symbols()
            raw = fetch_quotes(list(dict.fromkeys(requested)))
            normalized = {symbol: normalize(symbol, payload) for symbol, payload in raw.items()}
            roots = select_roots(normalized)
            archive(now, roots, normalized)
            fresh_exact = {symbol: q for symbol, q in normalized.items() if fresh(q, now)}
            fresh_roots = {root: q for root, q in roots.items() if fresh(q, now)}
            tracker.update(now, fresh_exact)
            decisions = []
            snapshot = {"timestamp": now, "roots": fresh_roots}
            for strategy in strategies:
                try:
                    decisions.extend(strategy.evaluate(snapshot))
                except Exception:
                    errors += 1
            tracker.open_decisions(decisions)
            decisions_count += len(decisions)
            status({"updated_at": now.isoformat(), "status": "RUNNING" if fresh_roots else "WAITING_FRESH_QUOTES", "strategies": len(strategies), "fresh_roots": sorted(fresh_roots), "active_contracts": {k: v["contractSymbol"] for k, v in roots.items()}, "active_paper_groups": len(tracker.active), "decisions": decisions_count, "errors": errors, "broker_execution_enabled": False})
        except Exception as exc:
            errors += 1
            status({"updated_at": now.isoformat(), "status": "ERROR_BACKOFF", "error": f"{type(exc).__name__}: {exc}", "strategies": len(strategies), "errors": errors, "broker_execution_enabled": False})
        time.sleep(max(1, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
