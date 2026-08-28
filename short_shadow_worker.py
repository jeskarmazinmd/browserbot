"""Isolated read-only Schwab worker for prospective short-only equity research."""
from __future__ import annotations

import gzip
import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from short_paper_tracker import ShortPaperTracker

NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "SMH", "IYT", "GLD", "SLV", "USO", "TLT", "NVDA", "AMD", "AVGO", "MSFT", "AAPL", "GOOGL", "META", "AMZN", "TSLA", "NFLX", "ORCL", "CRM", "MU", "INTC")
STRATEGIES = ("SHTBRK1", "SHTFAIL1", "SHTBRD1", "SHTGAP1", "SHTVOL1", "SHTMKT1")
QUOTE_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
TOKEN_PATH = Path("/data/schwab_token.json")
DATA_ROOT = Path("/data")
POLL_SECONDS = int(os.getenv("SHORT_SHADOW_POLL_SECONDS", "60"))
MAX_QUOTE_AGE_SECONDS = int(os.getenv("SHORT_MAX_QUOTE_AGE_SECONDS", "180"))


def _token():
    obj = json.loads(TOKEN_PATH.read_text())
    return obj.get("token", obj)["access_token"]


def fetch_quotes():
    response = requests.get(QUOTE_URL, headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"}, params={"symbols": ",".join(SYMBOLS)}, timeout=20)
    response.raise_for_status(); return response.json()


def normalize(symbol, payload):
    q = payload.get("quote") or {}; ref = payload.get("reference") or {}
    return {
        "symbol": symbol, "realtime": payload.get("realtime") is True,
        "bid": q.get("bidPrice"), "ask": q.get("askPrice"), "last": q.get("lastPrice"), "mark": q.get("mark"),
        "close": q.get("closePrice"), "bidSize": q.get("bidSize"), "askSize": q.get("askSize"),
        "quoteTime": q.get("quoteTime"), "tradeTime": q.get("tradeTime"),
        "totalVolume": q.get("totalVolume"), "securityStatus": q.get("securityStatus"),
        "description": ref.get("description"), "exchange": ref.get("exchangeName"),
    }


def fresh(q, now):
    try:
        age = abs(now.timestamp() - float(q["quoteTime"]) / 1000)
        return q.get("realtime") is True and float(q["bid"]) > 0 and float(q["ask"]) >= float(q["bid"]) and age <= MAX_QUOTE_AGE_SECONDS
    except Exception: return False


def regular_market(now):
    et = now.astimezone(NY); minute = et.hour * 60 + et.minute
    return et.weekday() < 5 and 570 <= minute < 960


def entry_window(now):
    et = now.astimezone(NY); minute = et.hour * 60 + et.minute
    return et.weekday() < 5 and 575 <= minute < 930


def archive(now, quotes):
    path = DATA_ROOT / "short_tapes" / f"short_quotes_{now:%Y%m%d}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at") as handle:
        handle.write(json.dumps({"timestamp": now.isoformat(), "quotes": quotes}, separators=(",", ":")) + "\n")


def status(payload):
    path = DATA_ROOT / "short_shadow_status.json"; tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n"); tmp.replace(path)


def load_strategies():
    result = []
    for sid in STRATEGIES:
        module = importlib.import_module(f"short_strategies.strategy_{sid.lower()}")
        assert module.PAPER_ONLY is True and module.LIVE_ORDER_PLACEMENT is False and module.SIDE == "SHORT"
        result.append(module.Strategy())
    return result


def main():
    tracker = ShortPaperTracker(DATA_ROOT); strategies = load_strategies(); errors = 0; decisions_count = 0
    while True:
        started = time.monotonic(); now = datetime.now(timezone.utc)
        try:
            raw = fetch_quotes(); normalized = {symbol: normalize(symbol, payload) for symbol, payload in raw.items() if symbol in SYMBOLS}
            if regular_market(now): archive(now, normalized)
            usable = {symbol: q for symbol, q in normalized.items() if fresh(q, now)}
            tracker.update(now, usable)
            decisions = []
            if entry_window(now):
                snapshot = {"timestamp": now, "quotes": usable}
                for strategy in strategies:
                    try: decisions.extend(strategy.evaluate(snapshot))
                    except Exception: errors += 1
            tracker.open_decisions(decisions); decisions_count += len(decisions)
            state = "RUNNING" if regular_market(now) and usable else ("WAITING_FRESH_QUOTES" if regular_market(now) else "WAITING_REGULAR_MARKET")
            status({"updated_at": now.isoformat(), "status": state, "strategies": len(strategies), "fresh_symbols": len(usable), "active_paper_shorts": len(tracker.active), "decisions": decisions_count, "errors": errors, "broker_execution_enabled": False})
        except Exception as exc:
            errors += 1
            status({"updated_at": now.isoformat(), "status": "ERROR_BACKOFF", "error": f"{type(exc).__name__}: {exc}", "strategies": len(strategies), "errors": errors, "broker_execution_enabled": False})
        time.sleep(max(1, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__": main()
