"""Isolated, paper-only top-of-book observer for live NH015 signals.

This process tails the public bot event stream and obtains read-only Schwab
quotes.  It deliberately imports neither the live runner nor any trading
client, and writes only its own observation/status files.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
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
MAX_CONCURRENT_OBSERVATIONS = int(
    os.environ.get("NH015_OBSERVER_MAX_CONCURRENT_OBSERVATIONS", "16")
)
MAX_INFLIGHT_OBSERVATIONS = int(
    os.environ.get("NH015_OBSERVER_MAX_INFLIGHT_OBSERVATIONS", "64")
)
_APPEND_LOCK = threading.Lock()
STABILITY_FAMILY_VERSION = "nh015_quote_stability_v1_20260905"
STABILITY_POLICY_IDS = (
    "C3N25S10NH015XBIDSTABLE250", "C3N25S10NH015XBIDUP250",
    "C3N25S10NH015XSTABLE1000", "C3N25S10NH015XSPREADCOMP",
    "C3N25S10NH015XASKPERSIST", "C3N25S10NH015XSIZE2X",
    "C3N25S10NH015XEDGE3STABLE", "C3N25S10NH015XDEPTHIMB",
)
LAST_PRICE_FAMILY_VERSION = "nh015_last_price_family_v1_20260905"
LAST_PRICE_POLICY_IDS = (
    "C3N25S10NH015XLASTIOC",
    "C3N25S10NH015XLAST250",
    "C3N25S10NH015XLAST1000",
)


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


def _valid_sample(sample):
    return (
        isinstance(sample, dict) and sample.get("outcome") != "UNKNOWN"
        and isinstance(sample.get("bid"), (int, float))
        and isinstance(sample.get("ask"), (int, float))
        and sample["bid"] > 0 and sample["ask"] >= sample["bid"]
    )


def _sample_spread_pct(sample):
    midpoint = (float(sample["bid"]) + float(sample["ask"])) / 2.0
    return ((float(sample["ask"]) - float(sample["bid"])) / midpoint) * 100.0


def evaluate_stability_policies(observations, limit_price, target_price, requested_qty):
    """Classify fixed sub-second gates from captured quote samples."""
    samples = {int(row.get("target_sample_delay_ms", -1)): row for row in observations}
    q0, q100, q250, q1000 = (samples.get(x) for x in (0, 100, 250, 1000))
    edge_pct = ((float(target_price) / float(limit_price)) - 1.0) * 100.0 if target_price and limit_price else None

    def marketable(q):
        return _valid_sample(q) and float(q["ask"]) <= float(limit_price)

    def result(strategy_id, admitted, sample, reason, **evidence):
        return {
            "strategy_id": strategy_id, "admitted": bool(admitted),
            "reason": reason,
            "simulated_entry_price": float(sample["ask"]) if admitted and _valid_sample(sample) else None,
            "decision_delay_ms": sample.get("target_sample_delay_ms") if isinstance(sample, dict) else None,
            "paper_only": True, "broker_execution_enabled": False, **evidence,
        }

    valid_0_250 = _valid_sample(q0) and _valid_sample(q250)
    bid_stable = valid_0_250 and float(q250["bid"]) >= float(q0["bid"])
    bid_up = valid_0_250 and float(q250["bid"]) > float(q0["bid"])
    contracted = valid_0_250 and _sample_spread_pct(q250) < _sample_spread_pct(q0)
    stable_1000 = (
        _valid_sample(q0) and _valid_sample(q1000)
        and float(q1000["bid"]) >= float(q0["bid"])
        and _sample_spread_pct(q1000) <= _sample_spread_pct(q0)
    )
    persistent = all(marketable(q) for q in (q0, q100, q250))
    size_2x = (
        marketable(q0) and q0.get("ask_size_raw") is not None
        and float(q0["ask_size_raw"]) * ASK_SIZE_MULTIPLIER >= 2 * int(requested_qty)
    )
    edge_stable = (
        bid_stable and marketable(q250) and edge_pct is not None
        and _sample_spread_pct(q250) * 3.0 <= edge_pct
    )
    return [
        result(STABILITY_POLICY_IDS[0], bid_stable and marketable(q250), q250, "BID_STABLE_AND_MARKETABLE" if bid_stable and marketable(q250) else "GATE_FAILED"),
        result(STABILITY_POLICY_IDS[1], bid_up and marketable(q250), q250, "BID_UP_AND_MARKETABLE" if bid_up and marketable(q250) else "GATE_FAILED"),
        result(STABILITY_POLICY_IDS[2], stable_1000 and marketable(q1000), q1000, "STABLE_THROUGH_1000MS" if stable_1000 and marketable(q1000) else "GATE_FAILED"),
        result(STABILITY_POLICY_IDS[3], contracted and marketable(q250), q250, "SPREAD_CONTRACTED" if contracted and marketable(q250) else "GATE_FAILED"),
        result(STABILITY_POLICY_IDS[4], persistent, q250, "ASK_PERSISTED" if persistent else "GATE_FAILED"),
        result(STABILITY_POLICY_IDS[5], size_2x, q0, "DISPLAYED_SIZE_AT_LEAST_2X" if size_2x else "GATE_FAILED", requested_qty=int(requested_qty), ask_size_multiplier=ASK_SIZE_MULTIPLIER),
        result(STABILITY_POLICY_IDS[6], edge_stable, q250, "EDGE_3X_AND_BID_STABLE" if edge_stable else "GATE_FAILED", signal_edge_pct=edge_pct, observed_spread_pct=_sample_spread_pct(q250) if _valid_sample(q250) else None),
        result(STABILITY_POLICY_IDS[7], False, None, "LEVEL2_NOT_CONNECTED"),
    ]


def evaluate_last_price_policies(observations, last_price, requested_qty):
    """Test fixed signal-LAST limits without assuming a queued passive fill.

    Each captured sample was already classified by ``estimate_ioc`` against
    the immutable signal price.  A policy is admitted only when a complete
    reference-size fill was demonstrably marketable at one of its permitted
    observation times.  The simulated entry remains the limit price, even if
    the observed ask was lower, so price improvement is never invented.
    """
    samples = {
        int(row.get("target_sample_delay_ms", -1)): row
        for row in observations
        if isinstance(row, dict)
    }

    def decision(strategy_id, horizon_ms):
        eligible_delays = sorted(
            delay for delay in samples
            if 0 <= delay <= int(horizon_ms)
        )
        fill_sample = next(
            (
                samples[delay]
                for delay in eligible_delays
                if samples[delay].get("outcome") == "FULL"
                and _valid_sample(samples[delay])
                and float(samples[delay]["ask"]) <= float(last_price)
                and int(samples[delay].get("estimated_fill_qty") or 0)
                >= int(requested_qty)
            ),
            None,
        )
        evidence = [
            {
                "delay_ms": delay,
                "outcome": samples[delay].get("outcome"),
                "reason": samples[delay].get("reason"),
                "ask": samples[delay].get("ask"),
                "estimated_fill_qty": samples[delay].get("estimated_fill_qty"),
            }
            for delay in eligible_delays
        ]
        if fill_sample is None:
            return {
                "strategy_id": strategy_id,
                "admitted": False,
                "reason": f"NO_FULL_FILL_BY_{int(horizon_ms)}MS",
                "limit_price": float(last_price),
                "requested_qty": int(requested_qty),
                "fill_deadline_ms": int(horizon_ms),
                "fill_evidence": evidence,
                "paper_only": True,
                "broker_execution_enabled": False,
            }
        return {
            "strategy_id": strategy_id,
            "admitted": True,
            "reason": "FULL_FILL_EVIDENCE_AT_OR_BELOW_LAST",
            "limit_price": float(last_price),
            "simulated_entry_price": float(last_price),
            "observed_ask": float(fill_sample["ask"]),
            "requested_qty": int(requested_qty),
            "estimated_fill_qty": int(fill_sample["estimated_fill_qty"]),
            "fill_delay_ms": int(fill_sample["target_sample_delay_ms"]),
            "fill_deadline_ms": int(horizon_ms),
            "fill_evidence": evidence,
            "paper_only": True,
            "broker_execution_enabled": False,
        }

    return [
        decision(LAST_PRICE_POLICY_IDS[0], 0),
        decision(LAST_PRICE_POLICY_IDS[1], 250),
        decision(LAST_PRICE_POLICY_IDS[2], 1000),
    ]


def _append(payload):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), default=str) + "\n"
    with _APPEND_LOCK:
        with OUTPUT_PATH.open("a") as handle:
            handle.write(encoded)


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


def observe_signal(event, detected_at=None):
    signal = event.get("signal") or {}
    symbol = str(event.get("symbol") or signal.get("symbol") or "").upper()
    setup_id = signal.get("setup_id") or signal.get("source_setup_id")
    limit_price = float(signal.get("entry_price") or 0)
    if not symbol or limit_price <= 0:
        raise ValueError("NH015 signal lacks symbol or entry price")
    signal_time = parse_utc(event["timestamp"])
    qty = reference_quantity(limit_price)
    detected_at = detected_at or utc_now()
    observer_started_at = utc_now()
    queue_delay_ms = (observer_started_at - detected_at).total_seconds() * 1000
    observations = []
    for delay_ms in SAMPLE_DELAYS_MS:
        target_at = detected_at + timedelta(milliseconds=delay_ms)
        remaining = (target_at - utc_now()).total_seconds()
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
                "sample_delay_from_detection_ms": round(
                    (observed_at - detected_at).total_seconds() * 1000, 3
                ),
                "sample_delay_from_signal_ms": round(
                    (observed_at - signal_time).total_seconds() * 1000, 3
                ),
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
    target_price = float(signal.get("target_price") or 0)
    payload = {
        "record_type": "SIGNAL_MARKET_REPLAY",
        "recorded_at": utc_now().isoformat(),
        "strategy_id": STRATEGY_ID,
        "setup_id": setup_id,
        "symbol": symbol,
        "signal_event_time": signal_time.isoformat(),
        "observer_detected_at": detected_at.isoformat(),
        "observer_started_at": observer_started_at.isoformat(),
        "observer_queue_delay_ms": round(queue_delay_ms, 3),
        "detection_delay_ms": round((detected_at - signal_time).total_seconds() * 1000, 3),
        "limit_price": limit_price,
        "reference_quantity": qty,
        "quantity_source": f"floor_${REFERENCE_NOTIONAL:g}_notional_at_limit",
        "observations": observations,
        "stability_family_version": STABILITY_FAMILY_VERSION,
        "stability_policy_decisions": evaluate_stability_policies(
            observations, limit_price, target_price, qty
        ),
        "last_price_family_version": LAST_PRICE_FAMILY_VERSION,
        "last_price_policy_decisions": evaluate_last_price_policies(
            observations, limit_price, qty
        ),
        "paper_only": True,
        "broker_execution_enabled": False,
    }
    _append(payload)
    return payload


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
    executor = ThreadPoolExecutor(
        max_workers=max(1, MAX_CONCURRENT_OBSERVATIONS),
        thread_name_prefix="nh015-observer",
    )
    inflight: set[Future] = set()

    def publish_status(status="RUNNING", **extra):
        _status(
            status=status,
            signals_seen=seen,
            observations=observations,
            reconciliations=reconciliations,
            errors=errors,
            inflight_observations=len(inflight),
            max_concurrent_observations=MAX_CONCURRENT_OBSERVATIONS,
            max_inflight_observations=MAX_INFLIGHT_OBSERVATIONS,
            **extra,
        )

    def reap_completed():
        nonlocal observations, errors
        for future in tuple(inflight):
            if not future.done():
                continue
            inflight.remove(future)
            try:
                future.result()
                observations += 1
            except Exception as exc:
                errors += 1
                _append({
                    "record_type": "OBSERVER_JOB_ERROR",
                    "recorded_at": utc_now().isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "paper_only": True,
                    "broker_execution_enabled": False,
                })

    with EVENTS_PATH.open() as stream:
        stream.seek(0, os.SEEK_END)  # prospective only; never reinterpret old events
        reconciliations = 0
        publish_status()
        while True:
            reap_completed()
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
                    detected_at = utc_now()
                    if len(inflight) >= max(1, MAX_INFLIGHT_OBSERVATIONS):
                        errors += 1
                        _append({
                            "record_type": "SIGNAL_OBSERVATION_DROPPED",
                            "recorded_at": detected_at.isoformat(),
                            "strategy_id": STRATEGY_ID,
                            "setup_id": (event.get("signal") or {}).get("setup_id"),
                            "symbol": event.get("symbol") or (event.get("signal") or {}).get("symbol"),
                            "reason": "OBSERVER_INFLIGHT_LIMIT",
                            "inflight_observations": len(inflight),
                            "paper_only": True,
                            "broker_execution_enabled": False,
                        })
                    else:
                        inflight.add(executor.submit(observe_signal, event, detected_at))
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
                publish_status()
            except Exception as exc:
                errors += 1
                publish_status(
                    "ERROR_CONTINUING",
                    last_error=f"{type(exc).__name__}: {exc}",
                )


if __name__ == "__main__":
    main()
