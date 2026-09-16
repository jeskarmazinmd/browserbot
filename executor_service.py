from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

from executor_broker import Broker, TOKEN_PATH, active_orders, position_quantity
from plugin_loader import load_plugin


ROOT = Path(os.environ.get("EXECUTOR_DATA_ROOT", "/data"))
AUDIT = ROOT / "executor_audit.jsonl"
HEALTH = ROOT / "executor_health.json"
SEEN = ROOT / "executor_seen_intents.json"


def truthy(name, default="false"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def csv_set(name):
    return frozenset(x.strip().upper() for x in os.environ.get(name, "").split(",") if x.strip())


def atomic_json(path, value):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    os.replace(temporary, path)


def audit(event, **fields):
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with AUDIT.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class Config:
    live_enabled: bool
    allowed_symbols: frozenset[str]
    allowed_strategy_id: str
    expected_plugin_hash: str
    max_notional: Decimal
    max_positions: int

    @classmethod
    def load(cls):
        config = cls(
            live_enabled=truthy("EXECUTOR_MANUAL_LIVE_ENABLED"),
            allowed_symbols=csv_set("EXECUTOR_ALLOWED_SYMBOLS"),
            allowed_strategy_id=os.environ.get("EXECUTOR_PLUGIN_STRATEGY_ID", "MANUAL_TEST1").strip().upper(),
            expected_plugin_hash=os.environ.get("EXECUTOR_PLUGIN_SHA256", "").strip().lower(),
            max_notional=Decimal(os.environ.get("EXECUTOR_MAX_NOTIONAL", "25")),
            max_positions=max(1, int(os.environ.get("EXECUTOR_MAX_POSITIONS", "1"))),
        )
        if config.live_enabled and not config.expected_plugin_hash:
            raise RuntimeError("live mode requires EXECUTOR_PLUGIN_SHA256")
        if config.live_enabled and not config.allowed_symbols:
            raise RuntimeError("live mode requires a non-empty symbol allowlist")
        return config


def regular_hours():
    now = datetime.now(ZoneInfo("America/New_York"))
    minute = now.hour * 60 + now.minute
    return now.weekday() < 5 and 570 <= minute < 960


def validate_intent(intent, config, now=None):
    now = now or datetime.now(timezone.utc)
    errors = []
    value = intent.to_dict()
    try:
        created = datetime.fromisoformat(value["created_at"])
        expires = datetime.fromisoformat(value["expires_at"])
        price = Decimal(value["limit_price"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return ["invalid_time_or_price"]
    if intent.strategy_id != config.allowed_strategy_id:
        errors.append("strategy_not_allowlisted")
    if intent.symbol.upper() not in config.allowed_symbols:
        errors.append("symbol_not_allowlisted")
    if intent.side not in {"BUY", "SELL"}:
        errors.append("invalid_side")
    if intent.quantity != 1:
        errors.append("quantity_must_equal_one")
    if price <= 0 or price > config.max_notional:
        errors.append("notional_out_of_bounds")
    timestamps_are_aware = created.tzinfo is not None and expires.tzinfo is not None
    if not timestamps_are_aware:
        errors.append("stale_or_invalid_window")
    elif now < created or now > expires:
        errors.append("stale_or_invalid_window")
    if timestamps_are_aware and (expires - created).total_seconds() > 60:
        errors.append("intent_window_too_long")
    return errors


class Runtime:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.plugin, self.manifest, self.plugin_hash = load_plugin(
            "/app/plugin", config.allowed_strategy_id, config.expected_plugin_hash
        )
        try:
            self.seen = set(json.loads(SEEN.read_text()))
        except Exception:
            self.seen = set()
        self.broker = None
        self.last_result = None
        self.publish(starting=True)

    def broker_client(self):
        if self.broker is None:
            self.broker = Broker()
        return self.broker

    def publish(self, **fields):
        value = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "OK",
            "phase": 2,
            "mode": "MANUAL_LIVE" if self.config.live_enabled else "DRY_RUN",
            "live_execution_enabled": self.config.live_enabled,
            "token_present": TOKEN_PATH.exists(),
            "strategy_id": self.config.allowed_strategy_id,
            "plugin_version": self.manifest.get("version"),
            "plugin_sha256": self.plugin_hash,
            "allowed_symbols": sorted(self.config.allowed_symbols),
            "max_notional": str(self.config.max_notional),
            "seen_intents": len(self.seen),
            "last_result": self.last_result,
            **fields,
        }
        atomic_json(HEALTH, value)

    def reconcile(self, broker, intent):
        positions = broker.positions()
        orders = broker.recent_orders(minutes=7 * 24 * 60)
        if not positions.get("ok") or not orders.get("ok"):
            raise RuntimeError("broker reconciliation failed")
        working = active_orders(orders.get("orders", []))
        if working:
            raise RuntimeError(f"active orders exist: {[x.get('orderId') for x in working]}")
        quantity = position_quantity(positions.get("positions", []), intent.symbol)
        if intent.side == "BUY":
            if quantity != 0:
                raise RuntimeError(f"existing symbol position quantity={quantity}")
            nonzero = [p for p in positions.get("positions", []) if float(p.get("longQuantity", 0) or 0) or float(p.get("shortQuantity", 0) or 0)]
            if len(nonzero) >= self.config.max_positions:
                raise RuntimeError("maximum positions reached")
        elif quantity < 1:
            raise RuntimeError(f"no long share available to sell; quantity={quantity}")

    def handle(self, intent):
        if intent.intent_id in self.seen:
            return
        self.seen.add(intent.intent_id)
        atomic_json(SEEN, sorted(self.seen))
        errors = validate_intent(intent, self.config)
        if errors:
            self.last_result = {"intent_id": intent.intent_id, "status": "REJECTED", "errors": errors}
            audit("INTENT_REJECTED", intent=intent.to_dict(), errors=errors)
            return
        if not regular_hours():
            self.last_result = {"intent_id": intent.intent_id, "status": "REJECTED", "errors": ["outside_regular_hours"]}
            audit("INTENT_REJECTED", intent=intent.to_dict(), errors=["outside_regular_hours"])
            return
        if not self.config.live_enabled:
            self.last_result = {"intent_id": intent.intent_id, "status": "VALIDATED_DRY_RUN"}
            audit("INTENT_VALIDATED_DRY_RUN", intent=intent.to_dict())
            return
        broker = self.broker_client()
        self.reconcile(broker, intent)
        response = broker.place_limit(intent.symbol, intent.side, intent.limit_price)
        location = response.get("headers", {}).get("location") or response.get("headers", {}).get("Location")
        order_id = str(location).rstrip("/").rsplit("/", 1)[-1] if location else None
        self.last_result = {
            "intent_id": intent.intent_id,
            "status": "SUBMITTED" if response.get("ok") else "SUBMISSION_FAILED",
            "status_code": response.get("status_code"),
            "order_id": order_id,
        }
        audit("ORDER_SUBMISSION_RESULT", intent=intent.to_dict(), result=self.last_result)

    def poll(self):
        with self.lock:
            for intent in self.plugin.evaluate({"now": datetime.now(timezone.utc).isoformat()}):
                try:
                    self.handle(intent)
                except Exception as exc:
                    self.last_result = {"intent_id": intent.intent_id, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
                    audit("INTENT_PROCESSING_ERROR", intent=intent.to_dict(), error=self.last_result["error"])
            self.publish()


class Handler(BaseHTTPRequestHandler):
    runtime = None

    def do_GET(self):
        if self.path not in {"/", "/health"}:
            self.send_error(404)
            return
        payload = HEALTH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    runtime = Runtime(Config.load())
    Handler.runtime = runtime
    audit("EXECUTOR_STARTED", plugin_sha256=runtime.plugin_hash, live_enabled=runtime.config.live_enabled)
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    while True:
        runtime.poll()
        time.sleep(1)


if __name__ == "__main__":
    main()
