"""Generic entry-safe feature discovery and profiling."""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_lab.provenance import safe_for_entry


IDENTITY_FIELDS={
    "strategy_id","symbol","setup_id","signal_timestamp",
    "entry","entry_price","target","target_price",
    "stop","stop_price","notional","paper_notional",
}


@dataclass
class FeatureProfile:
    strategy_id: str
    field: str
    kind: str
    count: int
    unique_count: int
    numeric_quantiles: dict[str,float]=field(default_factory=dict)
    categories: tuple[Any,...]=()
    outcomes: int=0


def flatten_scalars(value: Any,prefix="") -> dict[str,Any]:
    out={}

    if isinstance(value,dict):
        for key,child in value.items():
            name=f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child,dict):
                out.update(flatten_scalars(child,name))
            elif isinstance(child,list):
                # Lists are retained as opaque categorical values only when
                # simple; richer list transforms belong in feature plugins.
                if all(
                    isinstance(x,(str,int,float,bool,type(None)))
                    for x in child
                ):
                    out[name]=tuple(child)
            else:
                out[name]=child

    return out


def _records(path: Path):
    suffixes="".join(path.suffixes).lower()
    opener=gzip.open if suffixes.endswith(".gz") else open

    with opener(path,"rt",errors="replace") as handle:
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


def _quantile(values,q):
    if not values:
        return math.nan
    ordered=sorted(values)
    index=round((len(ordered)-1)*q)
    return float(ordered[index])


def profile_sources(
    sources,
    *,
    max_records_per_source: int | None=None,
):
    values=defaultdict(list)
    outcome_counts=defaultdict(int)

    for source in sources:
        if not (
            {"research_outcome","paper_outcome"} & source.roles
            and source.format in {"jsonl","jsonl.gz"}
        ):
            continue

        seen=0

        for row in _records(source.path):
            if (
                max_records_per_source is not None
                and seen>=max_records_per_source
            ):
                break
            seen+=1

            strategy=str(row.get("strategy_id") or "").strip()
            if not strategy:
                continue

            outcome=_outcome(row)
            flat=flatten_scalars(row)

            for field_name,value in flat.items():
                leaf=field_name.rsplit(".",1)[-1]

                if leaf in IDENTITY_FIELDS:
                    continue
                if not safe_for_entry(field_name):
                    continue
                if value is None:
                    continue

                values[(strategy,field_name)].append(value)
                if outcome is not None:
                    outcome_counts[(strategy,field_name)]+=1

    profiles=[]

    for (strategy,field_name),items in sorted(values.items()):
        numeric=[]
        categorical=[]

        for value in items:
            if isinstance(value,bool):
                categorical.append(value)
                continue
            try:
                number=float(value)
            except (TypeError,ValueError):
                categorical.append(value)
                continue
            if math.isfinite(number):
                numeric.append(number)

        if numeric and len(numeric)>=len(items)*0.90:
            qs={
                "q10":_quantile(numeric,.10),
                "q20":_quantile(numeric,.20),
                "q40":_quantile(numeric,.40),
                "q50":_quantile(numeric,.50),
                "q60":_quantile(numeric,.60),
                "q80":_quantile(numeric,.80),
                "q90":_quantile(numeric,.90),
            }
            profiles.append(FeatureProfile(
                strategy,
                field_name,
                "numeric",
                len(items),
                len(set(numeric)),
                numeric_quantiles=qs,
                outcomes=outcome_counts[(strategy,field_name)],
            ))
        else:
            unique=[]
            for value in categorical:
                try:
                    exists=value in unique
                except Exception:
                    exists=True
                if not exists:
                    unique.append(value)

            profiles.append(FeatureProfile(
                strategy,
                field_name,
                "categorical",
                len(items),
                len(unique),
                categories=tuple(unique[:20]),
                outcomes=outcome_counts[(strategy,field_name)],
            ))

    return profiles
