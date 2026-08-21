"""Concurrent-safe JSONL appends with verified intraday gzip rotation."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")


def _compress_verified(source: Path) -> Path:
    destination = source.with_suffix(source.suffix + ".gz")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    source_hash = hashlib.sha256()
    source_bytes = 0
    with source.open("rb") as raw, gzip.open(temporary, "wb", compresslevel=3) as compressed:
        while True:
            chunk = raw.read(1024 * 1024)
            if not chunk:
                break
            source_hash.update(chunk)
            source_bytes += len(chunk)
            compressed.write(chunk)

    restored_hash = hashlib.sha256()
    restored_bytes = 0
    with gzip.open(temporary, "rb") as restored:
        while True:
            chunk = restored.read(1024 * 1024)
            if not chunk:
                break
            restored_hash.update(chunk)
            restored_bytes += len(chunk)
    if restored_bytes != source_bytes or restored_hash.digest() != source_hash.digest():
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"gzip verification failed for {source}")
    os.replace(temporary, destination)
    source.unlink()
    return destination


def compress_pending(archive_root: Path) -> list[str]:
    """Recover immutable segments left uncompressed by an interrupted process."""
    compressed = []
    if not archive_root.exists():
        return compressed
    for source in sorted(archive_root.glob("*/*.jsonl")):
        compressed.append(str(_compress_verified(source)))
    return compressed


def append_jsonl(path, row, *, max_bytes: int, archive_root=None) -> dict:
    """Append one object, rotating the existing file before it exceeds its cap.

    All cooperating writers lock a separate inode before checking size, rename,
    or append.  Compression happens after unlocking because the renamed segment
    is immutable and new events can continue immediately in the active file.
    """
    path = Path(path)
    archive_root = Path(archive_root or (path.parent / "archive" / "intraday"))
    line = json.dumps(row, separators=(",", ":"), default=str) + "\n"
    encoded_size = len(line.encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    rotated = None

    with lock_path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current_size = path.stat().st_size if path.exists() else 0
        if current_size and current_size + encoded_size > int(max_bytes):
            now = datetime.now(timezone.utc)
            market_day = now.astimezone(NY).date().isoformat()
            directory = archive_root / market_day
            directory.mkdir(parents=True, exist_ok=True)
            stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
            rotated = directory / f"{path.stem}.{stamp}.{os.getpid()}.jsonl"
            os.replace(path, rotated)
        with path.open("a") as handle:
            handle.write(line)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    result = {"rotated": False, "archive": None, "compression_error": None}
    if rotated is not None:
        result["rotated"] = True
        try:
            result["archive"] = str(_compress_verified(rotated))
        except Exception as exc:
            # The raw immutable segment remains recoverable. Logging must not
            # bring down the strategy runner merely because compression failed.
            result["compression_error"] = f"{type(exc).__name__}: {exc}"
    return result
