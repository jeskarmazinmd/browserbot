"""Cross-process safety and durable status for Schwab token files."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path


class ManualReauthRequired(RuntimeError):
    pass


@contextmanager
def token_file_lock(token_path):
    lock_path = Path(str(token_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path, payload):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def is_terminal_refresh_error(error):
    text = str(error).lower()
    return any(marker in text for marker in (
        "invalid_grant",
        "refresh token is invalid",
        "refresh token is expired",
        "refresh token is revoked",
    ))


def mark_manual_reauth_required(token_path, status_path, error):
    token_path = Path(token_path)
    token_mtime_ns = token_path.stat().st_mtime_ns if token_path.exists() else None
    atomic_write_json(status_path, {
        "status": "MANUAL_REAUTH_REQUIRED",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "token_path": str(token_path),
        "token_mtime_ns": token_mtime_ns,
        "error_type": type(error).__name__,
        "reason": "Schwab rejected the trading refresh token",
    })


def manual_reauth_required(token_path, status_path):
    token_path = Path(token_path)
    status_path = Path(status_path)
    if not status_path.exists():
        return False
    try:
        status = json.loads(status_path.read_text())
        if status.get("status") != "MANUAL_REAUTH_REQUIRED":
            return False
        recorded = status.get("token_mtime_ns")
        current = token_path.stat().st_mtime_ns if token_path.exists() else None
        # A manual OAuth flow replaces/touches the token file.  That new file
        # automatically permits one fresh verification attempt.
        return recorded == current
    except Exception:
        return False


def clear_auth_failure(status_path):
    Path(status_path).unlink(missing_ok=True)
