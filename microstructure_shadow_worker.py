"""Isolated read-only Schwab worker for prospective top-of-book research."""
from __future__ import annotations

import gzip
import importlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from microstructure_paper_tracker import MicrostructurePaperTracker

NY = ZoneInfo("America/New_York")
SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU",
    "SMH", "IYT", "GLD", "SLV", "USO", "TLT", "NVDA", "AMD", "AVGO", "MSFT", "AAPL",
    "GOOGL", "META", "AMZN", "TSLA", "NFLX", "ORCL", "CRM", "MU", "INTC",
)
STRATEGIES = (
    "MSIMB1", "MSPERSIST1", "MSBIDPULL1", "MSFLIP1",
    "MSVEL1", "MSSPSHOCK1", "MSDEPTH1", "MSRECOV1",
)
QUOTE_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
TOKEN_PATH = Path(os.environ.get("MICROSTRUCTURE_MARKET_TOKEN", "/data/schwab_token.json"))
DATA_ROOT = Path(os.environ.get("MICROSTRUCTURE_DATA_ROOT", "/data"))
POLL_SECONDS = float(os.environ.get("MICROSTRUCTURE_POLL_SECONDS", "5"))
MAX_QUOTE_AGE_SECONDS = float(os.environ.get("MICROSTRUCTURE_MAX_QUOTE_AGE_SECONDS", "20"))
STATUS_PATH = DATA_ROOT / "microstructure_shadow_status.json"


def _token():
    obj = json.loads(TOKEN_PATH.read_text())
    token = obj.get("token", obj) if isinstance(obj, dict) else {}
    value = token.get("access_token") if isinstance(token, dict) else None
    if not value:
        raise RuntimeError("market access token unavailable")
    return str(value)


def fetch_quotes():
    import requests
    # This optional worker never creates/refreshed OAuth state and never reads
    # the trading token. It is strictly a read-only market-data consumer.
    r = requests.get(
        QUOTE_URL,
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
        params={"symbols": ",".join(SYMBOLS)}, timeout=20,
    )
    r.raise_for_status()
    return r.json()


def normalize(symbol, payload):
    q = payload.get("quote") or {}
    return {
        "symbol": str(symbol).upper(), "realtime": payload.get("realtime") is True,
        "bid": q.get("bidPrice"), "ask": q.get("askPrice"), "last": q.get("lastPrice"),
        "mark": q.get("mark"), "bid_size": q.get("bidSize"), "ask_size": q.get("askSize"),
        "quote_time_ms": q.get("quoteTime"), "bid_time_ms": q.get("bidTime"),
        "ask_time_ms": q.get("askTime"), "trade_time_ms": q.get("tradeTime"),
    }


def fresh(q, now):
    try:
        bid = float(q["bid"]); ask = float(q["ask"])
        age = abs(now.timestamp() - float(q["quote_time_ms"]) / 1000)
        return (
            q.get("realtime") is True and bid > 0 and ask >= bid
            and float(q.get("bid_size") or 0) >= 0 and float(q.get("ask_size") or 0) >= 0
            and age <= MAX_QUOTE_AGE_SECONDS
        )
    except Exception:
        return False


def regular_market(now):
    et = now.astimezone(NY); minute = et.hour * 60 + et.minute
    return et.weekday() < 5 and 570 <= minute < 960


def entry_window(now):
    et = now.astimezone(NY); minute = et.hour * 60 + et.minute
    return et.weekday() < 5 and 575 <= minute < 930


def _atomic(payload):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(STATUS_PATH)


def archive(now, quotes):
    path = DATA_ROOT / "microstructure_tapes" / f"top_book_{now:%Y%m%d}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at") as handle:
        handle.write(json.dumps({"timestamp": now.isoformat(), "quotes": quotes}, separators=(",", ":")) + "\n")


def load_strategies():
    result = []
    for sid in STRATEGIES:
        module = importlib.import_module(f"microstructure_strategies.strategy_{sid.lower()}")
        assert module.PAPER_ONLY is True
        assert module.LIVE_ORDER_PLACEMENT is False
        result.append(module.Strategy())
    return result


def main():
    tracker = MicrostructurePaperTracker(DATA_ROOT)
    strategies = load_strategies()
    decisions_total = 0; errors_total = 0; requests_total = 0
    print(f"MICROSTRUCTURE_SHADOW starting strategies={len(strategies)} symbols={len(SYMBOLS)} poll={POLL_SECONDS}s", flush=True)
    while True:
        started = time.monotonic(); now = datetime.now(timezone.utc)
        if not regular_market(now):
            _atomic({
                "updated_at": now.isoformat(), "status": "WAITING_REGULAR_MARKET",
                "strategies": len(strategies), "symbols": len(SYMBOLS), "fresh_symbols": 0,
                "active_paper_positions": len(tracker.active), "decisions": decisions_total,
                "errors": errors_total, "requests": requests_total, "poll_seconds": POLL_SECONDS,
                "broker_execution_enabled": False,
            })
            time.sleep(30)
            continue
        try:
            raw = fetch_quotes(); requests_total += 1
            quotes = {symbol: normalize(symbol, payload) for symbol, payload in raw.items() if symbol in SYMBOLS}
            usable = {symbol: q for symbol, q in quotes.items() if fresh(q, now)}
            if regular_market(now):
                archive(now, usable)
            tracker.update(now, usable)
            decisions = []
            if entry_window(now):
                snapshot = {"timestamp": now, "quotes": usable}
                for strategy in strategies:
                    try:
                        decisions.extend(strategy.evaluate(snapshot))
                    except Exception:
                        errors_total += 1
            tracker.open_decisions(decisions)
            decisions_total += len(decisions)
            if regular_market(now):
                state = "RUNNING" if usable else "WAITING_FRESH_QUOTES"
            else:
                state = "WAITING_REGULAR_MARKET"
            _atomic({
                "updated_at": now.isoformat(), "status": state,
                "strategies": len(strategies), "symbols": len(SYMBOLS), "fresh_symbols": len(usable),
                "active_paper_positions": len(tracker.active), "decisions": decisions_total,
                "errors": errors_total, "requests": requests_total, "poll_seconds": POLL_SECONDS,
                "broker_execution_enabled": False,
            })
        except Exception as exc:
            errors_total += 1
            _atomic({
                "updated_at": now.isoformat(), "status": "ERROR_BACKOFF",
                "error": f"{type(exc).__name__}: {exc}", "strategies": len(strategies),
                "errors": errors_total, "broker_execution_enabled": False,
            })
        time.sleep(max(1.0, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
