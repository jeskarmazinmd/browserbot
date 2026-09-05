"""Isolated, paper-only top-of-book observer for live NH015 signals.

This process tails the public bot event stream and obtains read-only Schwab
quotes.  It deliberately imports neither the live runner nor any trading
client, and writes only its own observation/status files.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from market_quotes import extract_quote_snapshot


STRATEGY_ID = "C3N25S10NH015"
QUOTE_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
DATA_ROOT = Path(os.environ.get("NH015_OBSERVER_DATA_ROOT", "/data"))
EVENTS_PATH = Path(os.environ.get("NH015_OBSERVER_EVENTS_PATH", DATA_ROOT / "bot_events.jsonl"))
TOKEN_PATH = Path(os.environ.get("NH015_OBSERVER_MARKET_TOKEN", "/data/schwab_token.json"))
OUTPUT_PATH = DATA_ROOT / "nh015_execution_observations.jsonl"
STATUS_PATH = DATA_ROOT / "nh015_execution_observer_status.json"
SAMPLE_DELAYS_MS = tuple(
    int(value.strip())
    for value in os.environ.get("NH015_OBSERVER_SAMPLE_DELAYS_MS", "0,100,250,500,1000").split(",")
    if value.strip()
)
MAX_QUOTE_AGE_MS = int(os.environ.get("NH015_OBSERVER_MAX_QUOTE_AGE_MS", "2000"))
REFERENCE_NOTIONAL = float(os.environ.get("NH015_OBSERVER_REFERENCE_NOTIONAL", "1000"))
ASK_SIZE_MULTIPLIER = float(os.environ.get("NH015_OBSERVER_ASK_SIZE_MULTIPLIER", "1"))


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def reference_quantity(limit_price):
    return max(0, math.floor(REFERENCE_NOTIONAL / float(limit_price)))


def estimate_ioc(snapshot, limit_price, requested_qty, signal_time, observed_at):
    """Classify only what top-of-book evidence supports; never invent a fill."""
    base = {
        "limit_price": float(limit_price),
        "requested_qty": int(requested_qty),
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "bid_size_raw": snapshot.bid_size_raw,
        "ask_size_raw": snapshot.ask_size_raw,
        "quote_time_ms": snapshot.quote_time_ms,
        "bid_time_ms": snapshot.bid_time_ms,
        "ask_time_ms": snapshot.ask_time_ms,
        "bid_mic": snapshot.bid_mic,
        "ask_mic": snapshot.ask_mic,
        "realtime": snapshot.realtime,
        "observed_at": observed_at.isoformat(),
        "observer_delay_ms": round((observed_at - signal_time).total_seconds() * 1000, 3),
        "paper_only": True,
        "broker_execution_enabled": False,
    }
    quote_ms = snapshot.ask_time_ms or snapshot.quote_time_ms
    if quote_ms is None:
        return {**base, "outcome": "UNKNOWN", "reason": "missing_quote_timestamp"}
    quote_age_ms = observed_at.timestamp() * 1000 - float(quote_ms)
    base["quote_age_ms"] = round(quote_age_ms, 3)
    if snapshot.realtime is not True:
        return {**base, "outcome": "UNKNOWN", "reason": "quote_not_marked_realtime"}
    if snapshot.bid is None or snapshot.ask is None or snapshot.bid <= 0 or snapshot.ask < snapshot.bid:
        return {**base, "outcome": "UNKNOWN", "reason": "invalid_top_of_book"}
    if quote_age_ms < -1000 or quote_age_ms > MAX_QUOTE_AGE_MS:
        return {**base, "outcome": "UNKNOWN", "reason": "stale_or_future_quote"}
    if snapshot.ask > float(limit_price):
        return {**base, "outcome": "ZERO", "reason": "ask_above_limit", "estimated_fill_qty": 0}
    if snapshot.ask_size_raw is None:
        return {
            **base, "outcome": "PRICE_MARKETABLE_SIZE_UNKNOWN",
            "reason": "ask_at_or_below_limit_but_size_missing",
            "estimated_fill_price": snapshot.ask,
        }
    displayed_qty = max(0, math.floor(float(snapshot.ask_size_raw) * ASK_SIZE_MULTIPLIER))
    fill_qty = min(int(requested_qty), displayed_qty)
    base.update({
        "displayed_ask_qty_assumed": displayed_qty,
        "ask_size_multiplier": ASK_SIZE_MULTIPLIER,
        "estimated_fill_qty": fill_qty,
        "estimated_fill_price": snapshot.ask if fill_qty else None,
    })
    if fill_qty <= 0:
        return {**base, "outcome": "ZERO", "reason": "no_displayed_ask_size"}
    if fill_qty < int(requested_qty):
        return {**base, "outcome": "PARTIAL", "reason": "displayed_ask_size_below_quantity"}
    return {**base, "outcome": "FULL", "reason": "marketable_with_displayed_size"}


def _access_token():
    payload = json.loads(TOKEN_PATH.read_text())
    token = payload.get("token", payload) if isinstance(payload, dict) else {}
    value = token.get("access_token") if isinstance(token, dict) else None
    if not value:
        raise RuntimeError("market access token unavailable")
    return str(value)


def fetch_snapshot(symbol):
    import requests

    response = requests.get(
        QUOTE_URL,
        headers={"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"},
        params={"symbols": symbol},
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    payload = body.get(symbol) or body.get(symbol.upper())
    if not isinstance(payload, dict):
        raise RuntimeError(f"quote response missing symbol {symbol}")
    return extract_quote_snapshot(symbol, payload)


def _append(payload):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")


def _status(**payload):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "updated_at": utc_now().isoformat(),
        "strategy_id": STRATEGY_ID,
        "paper_only": True,
        "broker_execution_enabled": False,
        **payload,
    }
    temporary = STATUS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(body, separators=(",", ":")) + "\n")
    temporary.replace(STATUS_PATH)


def observe_signal(event):
    signal = event.get("signal") or {}
    symbol = str(event.get("symbol") or signal.get("symbol") or "").upper()
    setup_id = signal.get("setup_id") or signal.get("source_setup_id")
    limit_price = float(signal.get("entry_price") or 0)
    if not symbol or limit_price <= 0:
        raise ValueError("NH015 signal lacks symbol or entry price")
    signal_time = parse_utc(event["timestamp"])
    qty = reference_quantity(limit_price)
    detected_at = utc_now()
    started = time.monotonic()
    observations = []
    for delay_ms in SAMPLE_DELAYS_MS:
        remaining = delay_ms / 1000 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
        requested_at = utc_now()
        try:
            snapshot = fetch_snapshot(symbol)
            observed_at = utc_now()
            result = estimate_ioc(snapshot, limit_price, qty, signal_time, observed_at)
            result.update({
                "target_sample_delay_ms": delay_ms,
                "request_latency_ms": round((observed_at - requested_at).total_seconds() * 1000, 3),
            })
        except Exception as exc:
            result = {
                "target_sample_delay_ms": delay_ms,
                "observed_at": utc_now().isoformat(),
                "outcome": "UNKNOWN",
                "reason": "quote_request_error",
                "error": f"{type(exc).__name__}: {exc}",
                "paper_only": True,
                "broker_execution_enabled": False,
            }
        observations.append(result)
    _append({
        "record_type": "SIGNAL_MARKET_REPLAY",
        "recorded_at": utc_now().isoformat(),
        "strategy_id": STRATEGY_ID,
        "setup_id": setup_id,
        "symbol": symbol,
        "signal_event_time": signal_time.isoformat(),
        "observer_detected_at": detected_at.isoformat(),
        "detection_delay_ms": round((detected_at - signal_time).total_seconds() * 1000, 3),
        "limit_price": limit_price,
        "reference_quantity": qty,
        "quantity_source": f"floor_${REFERENCE_NOTIONAL:g}_notional_at_limit",
        "observations": observations,
        "paper_only": True,
        "broker_execution_enabled": False,
    })


def relevant_signal(event):
    return event.get("event_type") == "SIGNAL" and event.get("strategy_id") == STRATEGY_ID


def reconciliation_event(event):
    position = event.get("position") or {}
    return (
        (event.get("strategy_id") == STRATEGY_ID or position.get("strategy_id") == STRATEGY_ID)
        and event.get("event_type") in {"IOC_ENTRY_ATTEMPT", "IOC_ENTRY_RESPONSE", "ENTRY_FILL_CONFIRMED"}
    )


def main():
    seen = errors = observations = 0
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.touch(exist_ok=True)
    with EVENTS_PATH.open() as stream:
        stream.seek(0, os.SEEK_END)  # prospective only; never reinterpret old events
        _status(status="RUNNING", observations=0, reconciliations=0, errors=0)
        reconciliations = 0
        while True:
            line = stream.readline()
            if not line:
                # bot_events.jsonl is bounded and may be atomically rotated.
                # Follow the replacement file without asking the producer to
                # coordinate with this optional consumer.
                try:
                    current = EVENTS_PATH.stat()
                    opened = os.fstat(stream.fileno())
                    if current.st_ino != opened.st_ino or current.st_size < stream.tell():
                        stream.close()
                        stream = EVENTS_PATH.open()
                except OSError:
                    pass
                time.sleep(0.02)
                continue
            try:
                event = json.loads(line)
                if relevant_signal(event):
                    seen += 1
                    observe_signal(event)
                    observations += 1
                elif reconciliation_event(event):
                    _append({
                        "record_type": "LIVE_BROKER_RECONCILIATION",
                        "recorded_at": utc_now().isoformat(),
                        "source_event": event,
                        "paper_only": True,
                        "broker_execution_enabled": False,
                    })
                    reconciliations += 1
                else:
                    continue
                _status(
                    status="RUNNING", signals_seen=seen, observations=observations,
                    reconciliations=reconciliations, errors=errors,
                )
            except Exception as exc:
                errors += 1
                _status(
                    status="ERROR_CONTINUING", signals_seen=seen, observations=observations,
                    reconciliations=reconciliations, errors=errors,
                    last_error=f"{type(exc).__name__}: {exc}",
                )


if __name__ == "__main__":
    main()
