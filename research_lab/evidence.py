"""Normalized relational evidence for broad strategy research."""

from __future__ import annotations

import gzip
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from research_lab.features import flatten_scalars
from research_lab.provenance import safe_for_entry


def parse_time(value):
    if value is None:
        return None
    try:
        result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError):
        return None
    if result.tzinfo is None:
        result=result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _records(path):
    suffixes="".join(path.suffixes).lower()
    opener=gzip.open if suffixes.endswith(".gz") else open
    try:
        handle=opener(path,"rt",errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                row=json.loads(line)
            except Exception:
                continue
            if isinstance(row,dict):
                yield row


def _outcome(row):
    for key in ("ret_pct","return_pct"):
        try:
            value=float(row[key])
        except (KeyError,TypeError,ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


@dataclass
class TradeEvidence:
    strategy_id: str
    symbol: str
    setup_id: str
    entry_time: datetime
    signal_time: datetime
    outcome_pct: float
    source_strategy_id: str | None=None
    entry_sequence: int | None=None
    entered: bool=True
    entry_price: float | None=None
    stop_price: float | None=None
    exit_price: float | None=None
    exit_time: datetime | None=None
    safe_fields: dict[str,Any]=field(default_factory=dict)
    source_paths: set[str]=field(default_factory=set)


@dataclass(frozen=True)
class RegimeEvidence:
    timestamp: datetime
    fields: dict[str,Any]
    source_path: str


@dataclass
class EvidenceIndex:
    trades: tuple[TradeEvidence,...]
    regimes: tuple[RegimeEvidence,...]
    near_misses: tuple[dict[str,Any],...]
    _regime_times: tuple[datetime,...]=field(init=False,repr=False)

    def __post_init__(self):
        self._regime_times=tuple(x.timestamp for x in self.regimes)

    def trades_by_strategy(self):
        result=defaultdict(list)
        for trade in self.trades:
            result[trade.strategy_id].append(trade)
        return dict(result)

    def regime_at(self, timestamp, max_age_seconds=900):
        if not self.regimes:
            return None

        index=bisect_right(self._regime_times,timestamp)-1
        if index<0:
            return None

        result=self.regimes[index]
        age=(timestamp-result.timestamp).total_seconds()

        if age<0 or age>max_age_seconds:
            return None
        return result

    def coincident_groups(self, min_strategies=2):
        """Same-symbol/same-signal-time overlap, regardless of lineage."""
        groups=defaultdict(list)

        for trade in self.trades:
            key=(trade.symbol,trade.signal_time.isoformat())
            groups[key].append(trade)

        return {
            key:items
            for key,items in groups.items()
            if len({x.strategy_id for x in items})>=min_strategies
        }

    def coincident_overlap_counts(self):
        counts=Counter()
        for items in self.coincident_groups().values():
            ids=sorted({x.strategy_id for x in items})
            for left,right in combinations(ids,2):
                counts[(left,right)]+=1
        return counts

    def controlled_sibling_groups(self):
        """Parent/children or children sharing an explicit source strategy."""
        result={}

        for (symbol,signal_time),items in self.coincident_groups().items():
            roots={
                x.source_strategy_id
                for x in items
                if x.source_strategy_id
            }

            for root in roots:
                members=[
                    x for x in items
                    if (
                        x.strategy_id==root
                        or x.source_strategy_id==root
                    )
                ]
                if len({x.strategy_id for x in members})<2:
                    continue
                key=(root,symbol,signal_time)
                result[key]=members

        return result

    def controlled_sibling_overlap_counts(self):
        counts=Counter()
        for items in self.controlled_sibling_groups().values():
            ids=sorted({x.strategy_id for x in items})
            for left,right in combinations(ids,2):
                counts[(left,right)]+=1
        return counts

    def summary(self):
        joined_regime=sum(
            self.regime_at(x.entry_time) is not None
            for x in self.trades
        )
        return {
            "trades":len(self.trades),
            "strategies":len({
                x.strategy_id for x in self.trades
            }),
            "regimes":len(self.regimes),
            "regime_joined_trades":joined_regime,
            "coincident_groups":len(self.coincident_groups()),
            "coincident_pairs":len(self.coincident_overlap_counts()),
            "controlled_sibling_groups":len(
                self.controlled_sibling_groups()
            ),
            "controlled_sibling_pairs":len(
                self.controlled_sibling_overlap_counts()
            ),
            "near_misses":len(self.near_misses),
        }


def _number(row,key):
    try:
        value=float(row[key])
    except (KeyError,TypeError,ValueError):
        return None
    return value if math.isfinite(value) else None


def build_evidence(sources, *, max_records_per_source=None):
    trades={}
    regimes=[]
    near_misses=[]

    for source in sources:
        if source.format not in {"jsonl","jsonl.gz"}:
            continue

        count=0
        sequence_by_setup={}
        next_sequence=0

        for row in _records(source.path):
            if (
                max_records_per_source is not None
                and count>=max_records_per_source
            ):
                break
            count+=1

            setup_for_sequence=str(row.get("setup_id") or "").strip()
            event=row.get("event_type")

            if (
                event=="PAPER_ENTRY"
                and setup_for_sequence
                and setup_for_sequence not in sequence_by_setup
            ):
                sequence_by_setup[setup_for_sequence]=next_sequence
                next_sequence+=1

            if "regime" in source.roles:
                timestamp=parse_time(
                    row.get("timestamp") or row.get("logged_at")
                )
                if timestamp is None:
                    continue

                flat=flatten_scalars(row)
                fields={
                    f"regime.{key}":value
                    for key,value in flat.items()
                    if key not in {"timestamp","logged_at"}
                    and value is not None
                }
                regimes.append(RegimeEvidence(
                    timestamp,
                    fields,
                    str(source.path),
                ))
                continue

            if "near_miss" in source.roles:
                near_misses.append({
                    "source_path":str(source.path),
                    "row":row,
                })

            if not (
                {"paper_outcome","research_outcome"} & source.roles
            ):
                continue

            outcome=_outcome(row)
            strategy=str(row.get("strategy_id") or "").strip()
            symbol=str(row.get("symbol") or "").strip()

            entered=row.get("entered",True) is not False

            if "entry_timestamp" in row:
                explicit_entry=parse_time(row.get("entry_timestamp"))
                if explicit_entry is None:
                    entered=False
                entry_time=explicit_entry
            elif (
                row.get("exit_model")=="second_leg"
                and row.get("second_leg_entry_time")
            ):
                entry_time=parse_time(row.get("second_leg_entry_time"))
            else:
                entry_time=parse_time(
                    row.get("signal_timestamp")
                    or row.get("timestamp")
                )

            signal_time=parse_time(
                row.get("signal_timestamp")
                or row.get("timestamp")
                or row.get("entry_timestamp")
            )

            if (
                outcome is None
                or not strategy
                or not symbol
                or not entered
                or entry_time is None
                or signal_time is None
            ):
                continue

            setup=str(row.get("setup_id") or "").strip()
            if not setup:
                setup=(
                    f"{strategy}|{symbol}|"
                    f"{signal_time.isoformat()}"
                )

            flat=flatten_scalars(row)
            safe={
                key:value for key,value in flat.items()
                if value is not None and safe_for_entry(key)
            }

            sequence=row.get("entry_sequence")
            if sequence is None:
                sequence=sequence_by_setup.get(setup)
            try:
                sequence=int(sequence) if sequence is not None else None
            except (TypeError,ValueError):
                sequence=None

            key=(strategy,setup)
            existing=trades.get(key)

            if existing is None:
                trades[key]=TradeEvidence(
                    strategy_id=strategy,
                    symbol=symbol,
                    setup_id=setup,
                    entry_time=entry_time,
                    signal_time=signal_time,
                    outcome_pct=outcome,
                    source_strategy_id=(
                        str(row.get("source_strategy_id")).strip()
                        if row.get("source_strategy_id")
                        else None
                    ),
                    entry_sequence=sequence,
                    entered=entered,
                    entry_price=(
                        _number(row,"entry_price")
                        if "entry_price" in row
                        else _number(row,"entry")
                    ),
                    stop_price=(
                        _number(row,"stop_price")
                        if "stop_price" in row
                        else _number(row,"stop")
                    ),
                    exit_price=_number(row,"exit_price"),
                    exit_time=parse_time(
                        row.get("exit_timestamp")
                        or row.get("exit_time")
                    ),
                    safe_fields=safe,
                    source_paths={str(source.path)},
                )
            else:
                for name,value in safe.items():
                    existing.safe_fields.setdefault(name,value)
                existing.source_paths.add(str(source.path))
                if (
                    existing.entry_sequence is None
                    and sequence is not None
                ):
                    existing.entry_sequence=sequence

    regimes.sort(key=lambda x:x.timestamp)
    ordered_trades=tuple(sorted(
        trades.values(),
        key=lambda x:(
            x.entry_time,
            x.strategy_id,
            x.setup_id,
        ),
    ))

    return EvidenceIndex(
        trades=ordered_trades,
        regimes=tuple(regimes),
        near_misses=tuple(near_misses),
    )
