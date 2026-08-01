from pathlib import Path
from datetime import datetime, timezone
import json

LOG_PATH = Path("/data/trade_events.jsonl")

def log_trade_event(event_type: str, **kwargs):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **kwargs,
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    print(f"[trade_log] {event_type} {kwargs.get('symbol', '')}", flush=True)
