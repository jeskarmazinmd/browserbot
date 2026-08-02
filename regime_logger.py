from pathlib import Path
import json
from datetime import datetime, timezone

from regime_detector import calculate_regime


REGIME_HISTORY = Path("/data/regime_history.jsonl")

_last_logged_minute = None


def log_regime(df):
    """
    Save periodic market regime snapshots for later research.

    This is observational only.
    It does not affect trading decisions.
    """

    global _last_logged_minute

    now = datetime.now(timezone.utc)

    # log every 5 minutes
    bucket = now.replace(
        minute=(now.minute // 5) * 5,
        second=0,
        microsecond=0,
    )

    if bucket == _last_logged_minute:
        return None

    _last_logged_minute = bucket

    regime = calculate_regime(df)

    regime["logged_at"] = now.isoformat()

    try:
        REGIME_HISTORY.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with REGIME_HISTORY.open("a") as f:
            f.write(
                json.dumps(regime)
                + "\n"
            )

        return regime

    except Exception as e:
        print(
            f"REGIME_LOG_ERROR {type(e).__name__}: {e}",
            flush=True,
        )

        return None


def latest_regime(df=None):
    """
    Return latest saved regime.
    """

    try:
        if not REGIME_HISTORY.exists():
            return None

        with REGIME_HISTORY.open() as f:
            lines = f.readlines()

        if not lines:
            return None

        return json.loads(lines[-1])

    except Exception:
        return None
