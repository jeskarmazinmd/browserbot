"""Isolated read-only Schwab spot-FX research worker."""
from __future__ import annotations

import gzip
import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from forex_paper_tracker import ForexPaperTracker

PAIRS = ("EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "NZD/USD", "USD/CHF", "EUR/GBP")
STRATEGIES = ("FXEUR1", "FXGBP1", "FXJPY1", "FXAUD1", "FXCAD1", "FXCHF1", "FXEGBP1", "FXAN1", "FXUSDB1", "FXLON1")
QUOTE_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
TOKEN_PATH = Path("/data/schwab_token.json")
DATA_ROOT = Path("/data")
POLL_SECONDS = int(os.getenv("FOREX_SHADOW_POLL_SECONDS", "60"))
MAX_QUOTE_AGE_SECONDS = int(os.getenv("FOREX_MAX_QUOTE_AGE_SECONDS", "180"))


def _token():
    obj = json.loads(TOKEN_PATH.read_text())
    return obj.get("token", obj)["access_token"]


def fetch_quotes():
    response = requests.get(
        QUOTE_URL,
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
        params={"symbols": ",".join(PAIRS)}, timeout=20,
    )
    response.raise_for_status()
    return response.json()


def normalize(symbol, payload):
    q = payload.get("quote") or {}
    ref = payload.get("reference") or {}
    return {
        "symbol": symbol, "realtime": payload.get("realtime") is True,
        "tradable": ref.get("isTradable") is True,
        "bid": q.get("bidPrice"), "ask": q.get("askPrice"), "last": q.get("lastPrice"), "mark": q.get("mark"),
        "bidSize": q.get("bidSize"), "askSize": q.get("askSize"),
        "quoteTime": q.get("quoteTime"), "tradeTime": q.get("tradeTime"),
        "totalVolume": q.get("totalVolume"), "securityStatus": q.get("securityStatus"),
        "description": ref.get("description"), "exchange": ref.get("exchangeName"),
    }


def fresh(q, now):
    try:
        age = abs(now.timestamp() - float(q["quoteTime"]) / 1000)
        # isTradable is recorded separately because an account entitlement
        # should not prevent paper research when the market feed itself is
        # realtime.  There is no broker execution path in this worker.
        return q.get("realtime") is True and float(q["bid"]) > 0 and float(q["ask"]) >= float(q["bid"]) and age <= MAX_QUOTE_AGE_SECONDS
    except Exception:
        return False


def archive(now, pairs):
    path = DATA_ROOT / "forex_tapes" / f"forex_quotes_{now:%Y%m%d}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at") as handle:
        handle.write(json.dumps({"timestamp": now.isoformat(), "pairs": pairs}, separators=(",", ":")) + "\n")


def status(payload):
    path = DATA_ROOT / "forex_shadow_status.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(path)


def load_strategies():
    result = []
    for sid in STRATEGIES:
        module = importlib.import_module(f"forex_strategies.strategy_{sid.lower()}")
        assert module.PAPER_ONLY is True and module.LIVE_ORDER_PLACEMENT is False
        result.append(module.Strategy())
    return result


def main():
    tracker = ForexPaperTracker(DATA_ROOT)
    strategies = load_strategies()
    errors = 0
    decisions_count = 0
    while True:
        started = time.monotonic()
        now = datetime.now(timezone.utc)
        try:
            raw = fetch_quotes()
            normalized = {symbol: normalize(symbol, payload) for symbol, payload in raw.items() if symbol in PAIRS}
            archive(now, normalized)
            usable = {symbol: q for symbol, q in normalized.items() if fresh(q, now)}
            tracker.update(now, usable)
            decisions = []
            snapshot = {"timestamp": now, "pairs": usable}
            for strategy in strategies:
                try:
                    decisions.extend(strategy.evaluate(snapshot))
                except Exception:
                    errors += 1
            tracker.open_decisions(decisions)
            decisions_count += len(decisions)
            status({
                "updated_at": now.isoformat(), "status": "RUNNING" if usable else "WAITING_FRESH_QUOTES",
                "strategies": len(strategies), "fresh_pairs": sorted(usable),
                "tradable_pairs": sorted(symbol for symbol, q in normalized.items() if q.get("tradable") is True),
                "active_paper_groups": len(tracker.active), "decisions": decisions_count,
                "errors": errors, "broker_execution_enabled": False,
            })
        except Exception as exc:
            errors += 1
            status({
                "updated_at": now.isoformat(), "status": "ERROR_BACKOFF",
                "error": f"{type(exc).__name__}: {exc}", "strategies": len(strategies),
                "errors": errors, "broker_execution_enabled": False,
            })
        time.sleep(max(1, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
