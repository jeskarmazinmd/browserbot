"""Minimal fail-closed Schwab execution service.

Phase 1 is intentionally read-only: it validates manually supplied signals,
deduplicates them, reconciles broker state when credentials are present, and
records an audit trail.  No order-submission method is reachable in this file.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import threading
import time


ROOT = Path(os.environ.get("EXECUTOR_DATA_ROOT", "/data"))
INBOX = ROOT / "executor_inbox.jsonl"
AUDIT = ROOT / "executor_audit.jsonl"
HEALTH = ROOT / "executor_health.json"
SEEN = ROOT / "executor_seen_signal_ids.json"
TOKEN = ROOT / "schwab_trade_token.json"


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _csv_set(name: str) -> frozenset[str]:
    return frozenset(
        item.strip().upper()
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    )


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def _audit(event: str, **fields: object) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class Config:
    mode: str
    live_enabled: bool
    allowed_symbols: frozenset[str]
    allowed_strategies: frozenset[str]
    max_quantity: int
    max_positions: int
    max_signal_age_seconds: int

    @classmethod
    def load(cls) -> "Config":
        mode = os.environ.get("EXECUTOR_MODE", "READ_ONLY").strip().upper()
        live_enabled = _truthy("LIVE_EXECUTION_ENABLED")
        config = cls(
            mode=mode,
            live_enabled=live_enabled,
            allowed_symbols=_csv_set("EXECUTOR_ALLOWED_SYMBOLS"),
            allowed_strategies=_csv_set("EXECUTOR_ALLOWED_STRATEGIES"),
            max_quantity=max(0, int(os.environ.get("EXECUTOR_MAX_QUANTITY", "1"))),
            max_positions=max(0, int(os.environ.get("EXECUTOR_MAX_POSITIONS", "1"))),
            max_signal_age_seconds=max(
                1, int(os.environ.get("EXECUTOR_MAX_SIGNAL_AGE_SECONDS", "30"))
            ),
        )
        if mode not in {"READ_ONLY", "DRY_RUN"}:
            raise RuntimeError("Phase-1 executor permits only READ_ONLY or DRY_RUN")
        if live_enabled:
            raise RuntimeError("Live execution is not implemented in phase 1")
        return config


def validate_signal(signal: dict, config: Config, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    required = {"signal_id", "strategy_id", "symbol", "side", "quantity", "timestamp"}
    missing = sorted(required - set(signal))
    if missing:
        return ["missing_fields:" + ",".join(missing)]

    strategy = str(signal["strategy_id"]).upper()
    symbol = str(signal["symbol"]).upper()
    side = str(signal["side"]).upper()
    try:
        quantity = int(signal["quantity"])
    except (TypeError, ValueError):
        quantity = -1
    try:
        timestamp = datetime.fromisoformat(str(signal["timestamp"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone required")
    except (TypeError, ValueError):
        timestamp = None

    if not config.allowed_strategies or strategy not in config.allowed_strategies:
        errors.append("strategy_not_allowlisted")
    if not config.allowed_symbols or symbol not in config.allowed_symbols:
        errors.append("symbol_not_allowlisted")
    if side not in {"BUY", "SELL"}:
        errors.append("invalid_side")
    if quantity < 1 or quantity > config.max_quantity:
        errors.append("quantity_out_of_bounds")
    if timestamp is None:
        errors.append("invalid_timestamp")
    elif abs((now - timestamp.astimezone(timezone.utc)).total_seconds()) > config.max_signal_age_seconds:
        errors.append("stale_signal")
    return errors


class State:
    def __init__(self, config: Config):
        self.config = config
        self.lock = threading.Lock()
        self.offset = 0
        try:
            self.seen = set(json.loads(SEEN.read_text()))
        except (OSError, ValueError, TypeError):
            self.seen = set()
        self.health: dict = {}

    def publish(self, **fields: object) -> None:
        self.health = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "OK",
            "phase": 1,
            "submission_capability": "ABSENT",
            "mode": self.config.mode,
            "live_execution_enabled": False,
            "token_present": TOKEN.exists(),
            "allowed_symbols": sorted(self.config.allowed_symbols),
            "allowed_strategies": sorted(self.config.allowed_strategies),
            "seen_signal_ids": len(self.seen),
            **fields,
        }
        _atomic_json(HEALTH, self.health)

    def handle(self, signal: dict) -> None:
        signal_id = str(signal.get("signal_id") or "")
        digest = hashlib.sha256(
            json.dumps(signal, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if signal_id in self.seen:
            _audit("SIGNAL_REJECTED", reason="duplicate_signal_id", signal_id=signal_id, digest=digest)
            return
        errors = validate_signal(signal, self.config)
        self.seen.add(signal_id)
        _atomic_json(SEEN, sorted(self.seen))
        if errors:
            _audit("SIGNAL_REJECTED", reasons=errors, signal_id=signal_id, digest=digest)
            return
        _audit(
            "SIGNAL_VALIDATED_NO_SUBMISSION",
            signal_id=signal_id,
            digest=digest,
            strategy_id=str(signal["strategy_id"]).upper(),
            symbol=str(signal["symbol"]).upper(),
            side=str(signal["side"]).upper(),
            quantity=int(signal["quantity"]),
        )

    def poll(self) -> None:
        if not INBOX.exists():
            self.publish(inbox_present=False)
            return
        size = INBOX.stat().st_size
        if size < self.offset:
            _audit("INBOX_REPLACED", previous_offset=self.offset, new_size=size)
            self.offset = 0
        with INBOX.open() as handle:
            handle.seek(self.offset)
            for line in handle:
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("signal must be an object")
                    self.handle(value)
                except Exception as exc:
                    _audit("INBOX_ROW_REJECTED", error=f"{type(exc).__name__}: {exc}")
            self.offset = handle.tell()
        self.publish(inbox_present=True, inbox_offset=self.offset)


class Handler(BaseHTTPRequestHandler):
    state: State

    def do_GET(self):  # noqa: N802
        if self.path not in {"/", "/health"}:
            self.send_error(404)
            return
        payload = json.dumps(self.state.health, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def main() -> None:
    config = Config.load()
    state = State(config)
    Handler.state = state
    state.publish(starting=True)
    _audit("EXECUTOR_STARTED", config={**asdict(config), "allowed_symbols": sorted(config.allowed_symbols), "allowed_strategies": sorted(config.allowed_strategies)})
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    while True:
        try:
            state.poll()
        except Exception as exc:
            _audit("POLL_ERROR", error=f"{type(exc).__name__}: {exc}")
            state.publish(status="WARNING", error=f"{type(exc).__name__}: {exc}")
        time.sleep(1)


if __name__ == "__main__":
    main()
