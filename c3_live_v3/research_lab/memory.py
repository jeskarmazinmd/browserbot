"""Durable memory of research hypotheses and results."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def hypothesis_id(
    strategy_id: str,
    dimension: str,
    specification: dict[str, Any],
) -> str:
    payload={
        "strategy_id":str(strategy_id),
        "dimension":str(dimension),
        "specification":specification,
    }
    raw=json.dumps(
        payload,
        sort_keys=True,
        separators=(",",":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


class ResearchMemory:
    def __init__(self,path):
        self.path=Path(path)

    def load(self):
        if not self.path.exists():
            return []

        rows=[]
        with self.path.open(errors="replace") as handle:
            for line in handle:
                try:
                    row=json.loads(line)
                except Exception:
                    continue
                if isinstance(row,dict):
                    rows.append(row)
        return rows

    def known_ids(self):
        return {
            str(row.get("hypothesis_id"))
            for row in self.load()
            if row.get("hypothesis_id")
        }

    def record(
        self,
        strategy_id: str,
        dimension: str,
        specification: dict[str,Any],
        *,
        status: str,
        metrics: dict[str,Any] | None=None,
        evidence: dict[str,Any] | None=None,
        notes: str="",
        scope: str="exact_hypothesis",
    ):
        hid=hypothesis_id(
            strategy_id,
            dimension,
            specification,
        )

        if hid in self.known_ids():
            raise ValueError(
                f"hypothesis already recorded: {hid}"
            )

        row={
            "hypothesis_id":hid,
            "strategy_id":str(strategy_id),
            "dimension":str(dimension),
            "specification":specification,
            "status":str(status),
            "metrics":metrics or {},
            "evidence":evidence or {},
            "notes":str(notes),
            "scope":str(scope),
            "recorded_at":datetime.now(timezone.utc).isoformat(),
        }

        self.path.parent.mkdir(parents=True,exist_ok=True)

        with self.path.open("a") as handle:
            handle.write(
                json.dumps(row,sort_keys=True)
                +"\n"
            )

        return row
