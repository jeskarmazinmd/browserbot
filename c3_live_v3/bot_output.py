from pathlib import Path
from datetime import datetime, timezone
import json
import os

from bounded_jsonl import append_jsonl

RUN_MODE = os.environ.get("RUN_MODE", "LIVE")
RUN_ID = os.environ.get("RUN_ID", "live")

if RUN_MODE == "REPLAY":
    OUTPUT_ROOT = Path("./replay") / RUN_ID
else:
    OUTPUT_ROOT = Path("/data")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

HISTORY_JSONL = OUTPUT_ROOT / "bot_history.jsonl"
EVENTS_JSONL = OUTPUT_ROOT / "bot_events.jsonl"
INTRADAY_ARCHIVE = OUTPUT_ROOT / "archive" / "intraday"
EVENTS_MAX_BYTES = int(os.environ.get("BOT_EVENTS_MAX_BYTES", str(128 * 1024 * 1024)))
HISTORY_MAX_BYTES = int(os.environ.get("BOT_HISTORY_MAX_BYTES", str(32 * 1024 * 1024)))

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

    result = append_jsonl(
        HISTORY_JSONL,
        row,
        max_bytes=HISTORY_MAX_BYTES,
        archive_root=INTRADAY_ARCHIVE,
    )
    if result.get("compression_error"):
        print(f"HISTORY_ROTATION_WARNING {result['compression_error']}", flush=True)
    elif result.get("rotated"):
        print(f"HISTORY_LOG_ROTATED archive={result['archive']}", flush=True)

def append_bot_event(event_type, **kwargs):
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **kwargs,
    }
    result = append_jsonl(
        EVENTS_JSONL,
        row,
        max_bytes=EVENTS_MAX_BYTES,
        archive_root=INTRADAY_ARCHIVE,
    )
    if result.get("compression_error"):
        print(f"EVENT_ROTATION_WARNING {result['compression_error']}", flush=True)
    elif result.get("rotated"):
        print(f"EVENT_LOG_ROTATED archive={result['archive']}", flush=True)
