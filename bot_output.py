from pathlib import Path
from datetime import datetime, timezone
import json
import os

RUN_MODE = os.environ.get("RUN_MODE", "LIVE")
RUN_ID = os.environ.get("RUN_ID", "live")

if RUN_MODE == "REPLAY":
    OUTPUT_ROOT = Path("./replay") / RUN_ID
else:
    OUTPUT_ROOT = Path("/data")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

HISTORY_JSONL = OUTPUT_ROOT / "bot_history.jsonl"
EVENTS_JSONL = OUTPUT_ROOT / "bot_events.jsonl"

def write_bot_output(status="running", triggers=None, nearest=None, note=None):
    triggers = triggers or []
    nearest = nearest or []
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    row = {
        "timestamp": now,
        "date": today,
        "status": status,
        "latest_nearest": nearest[:5],
        "top_nearest_today": nearest[:5],
        "latest_triggers": triggers[:10],
        "total_triggers_today": len(triggers),
        "note": note,
    }

    HISTORY_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_JSONL.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")

def append_bot_event(event_type, **kwargs):
    EVENTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **kwargs,
    }
    with EVENTS_JSONL.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
