"""Prospective, paper-only adaptive cross-symbol shadow worker.

This process has no broker client and no order path.  It reads the minute cache,
freezes compact predictions, and leaves outcome scoring to later evidence jobs.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time as clock_time, timezone
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import pandas as pd

from research_lab.xs_evaluator import XSEvaluationPolicy, select_opportunities
from research_lab.xs_executor import XSSharedRuntime
from research_lab.xs_lifecycle import new_experiment
from research_lab.xs_shadows import compute_plan, ready_shadow_specs


NY=ZoneInfo("America/New_York")
DATA_ROOT=Path(os.environ.get("XS_DATA_ROOT","/data"))
MANIFEST_PATH=DATA_ROOT/"xs_shadow_manifest.json"
PREDICTION_PATH=DATA_ROOT/"xs_shadow_predictions.jsonl"
STATUS_PATH=DATA_ROOT/"xs_shadow_status.json"
MAX_LOG_BYTES=int(os.environ.get("XS_MAX_LOG_BYTES",5*1024*1024))
MAX_RSS_MIB=float(os.environ.get("XS_MAX_RSS_MIB","900"))
MAX_UPDATE_SECONDS=float(os.environ.get("XS_MAX_UPDATE_SECONDS","15"))
POLL_SECONDS=float(os.environ.get("XS_POLL_SECONDS","5"))
SELECTION_POLICY=XSEvaluationPolicy(
    long_only=True,
    min_prediction_bps=5.0,
    max_opportunities_per_minute=2,
)


def _utc(value):
    result=pd.Timestamp(value)
    return result.tz_localize("UTC") if result.tzinfo is None else result.tz_convert("UTC")


def cache_path(now):
    day=_utc(now).strftime("%Y%m%d")
    return DATA_ROOT/f"minute_quote_cache_{day}.pkl"


def cache_signature(path):
    """Cheaply identify a cache revision without deserializing the pickle."""
    stat=Path(path).stat()
    return (str(Path(path)),stat.st_mtime_ns,stat.st_size)


def load_minute_cache(path):
    frame=pd.read_pickle(path)
    required={"timestamp","symbol","price"}
    if not isinstance(frame,pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError("unexpected minute-cache schema")
    return frame[["timestamp","symbol","price"]].copy()


def complete_regular_prices(frame,now):
    """Pivot only completed regular-session minutes known at ``now``."""
    work=frame.copy()
    work["timestamp"]=pd.to_datetime(work["timestamp"],errors="coerce",utc=True)
    work["price"]=pd.to_numeric(work["price"],errors="coerce")
    work=work.dropna(subset=["timestamp","symbol","price"])
    cutoff=_utc(now).floor("min")
    work=work[work["timestamp"] < cutoff]
    if work.empty:
        return pd.DataFrame()
    local=work["timestamp"].dt.tz_convert(NY)
    regular=(
        (local.dt.weekday < 5)
        & (local.dt.time >= clock_time(9,30))
        & (local.dt.time < clock_time(16,0))
    )
    work=work.loc[regular]
    if work.empty:
        return pd.DataFrame()
    return work.pivot_table(
        index="timestamp",columns="symbol",values="price",aggfunc="last"
    ).sort_index()


def ensure_manifest(path,specs,now):
    """Preserve old births; newly changed specifications get new identities."""
    path=Path(path)
    existing=[]
    if path.exists():
        try:
            value=json.loads(path.read_text())
            if isinstance(value,list):
                existing=[x for x in value if isinstance(x,dict)]
        except Exception:
            existing=[]
    by_id={str(x.get("experiment_id")):x for x in existing if x.get("experiment_id")}
    active={}
    for spec in specs:
        specification={
            "shadow_name":spec.name,
            "engine":spec.engine,
            "config":asdict(spec.config),
        }
        candidate=new_experiment(spec.dimension,specification,born_at=now)
        row=by_id.get(candidate.experiment_id)
        if row is None:
            row={
                "experiment_id":candidate.experiment_id,
                "family":candidate.family,
                "specification":candidate.specification,
                "born_at":candidate.born_at,
            }
            existing.append(row)
            by_id[candidate.experiment_id]=row
        active[spec.name]=row
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(existing,indent=2,sort_keys=True)+"\n")
    os.replace(temporary,path)
    return active


def _append_prediction(row):
    from bounded_jsonl import append_jsonl
    return append_jsonl(PREDICTION_PATH,row,max_bytes=MAX_LOG_BYTES)


def _write_status(**values):
    payload={"updated_at":datetime.now(timezone.utc).isoformat(),**values}
    STATUS_PATH.parent.mkdir(parents=True,exist_ok=True)
    temporary=STATUS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload,sort_keys=True)+"\n")
    os.replace(temporary,STATUS_PATH)


def freeze_predictions(predictions,wide,manifest,writer=_append_prediction):
    """Select compact entry-time opportunities and append immutable decisions."""
    if predictions is None or predictions.empty:
        return 0
    count=0
    for shadow_name,group in predictions.groupby("shadow_name",sort=True):
        selected=select_opportunities(group,SELECTION_POLICY)
        experiment=manifest.get(str(shadow_name))
        if experiment is None:
            continue
        for item in selected.to_dict("records"):
            decision=_utc(item["decision_time"])
            target=str(item["target"])
            price=None
            if decision in wide.index and target in wide.columns:
                value=wide.at[decision,target]
                if pd.notna(value):
                    price=float(value)
            writer({
                "event_type":"XS_SHADOW_PREDICTION",
                "recorded_at":datetime.now(timezone.utc).isoformat(),
                "experiment_id":experiment["experiment_id"],
                "born_at":experiment["born_at"],
                "shadow_name":shadow_name,
                "decision_time":decision.isoformat(),
                "target":target,
                "decision_price":price,
                "predicted_return":float(item["predicted_return"]),
                "leaders":item["leaders"],
                "correlations":item["correlations"],
                "relationship_selected_at":str(item["relationship_selected_at"]),
                "side":"LONG",
            })
            count+=1
    return count


def main():
    import psutil

    specs=ready_shadow_specs()
    runtime=XSSharedRuntime(specs)
    manifest=ensure_manifest(MANIFEST_PATH,specs,datetime.now(timezone.utc))
    process=psutil.Process()
    last_minute=None
    last_cache_signature=None
    predictions_total=0
    paused_day=None
    print(f"XS_SHADOW starting experiments={len(specs)}",flush=True)

    while True:
        now=datetime.now(timezone.utc)
        market_day=now.astimezone(NY).date().isoformat()
        if paused_day==market_day:
            time.sleep(30)
            continue
        if paused_day is not None and paused_day!=market_day:
            paused_day=None

        path=cache_path(now)
        if not path.exists():
            _write_status(status="WAITING_CACHE",experiments=len(specs))
            time.sleep(POLL_SECONDS)
            continue

        try:
            signature=cache_signature(path)
            if signature==last_cache_signature:
                time.sleep(POLL_SECONDS)
                continue
            frame=load_minute_cache(path)
            last_cache_signature=signature
            wide=complete_regular_prices(frame,now)
            if wide.empty:
                _write_status(status="WAITING_REGULAR_HISTORY",experiments=len(specs))
                time.sleep(POLL_SECONDS)
                continue
            latest=wide.index[-1]
            if latest==last_minute:
                time.sleep(POLL_SECONDS)
                continue

            plan=compute_plan(wide.shape[1],specs)
            if not plan.allowed:
                paused_day=market_day
                _write_status(status="PAUSED_RESOURCE",reason=plan.reason)
                continue

            started=time.perf_counter()
            predictions=runtime.update(wide)
            emitted=freeze_predictions(predictions,wide,manifest)
            elapsed=time.perf_counter()-started
            predictions_total+=emitted
            rss=process.memory_info().rss/(1024**2)
            last_minute=latest
            if rss > MAX_RSS_MIB or elapsed > MAX_UPDATE_SECONDS:
                paused_day=market_day
                reason=(
                    f"rss_mib={rss:.1f} limit={MAX_RSS_MIB:.1f}; "
                    f"update_seconds={elapsed:.3f} limit={MAX_UPDATE_SECONDS:.3f}"
                )
                _write_status(status="PAUSED_RESOURCE",reason=reason)
                print(f"XS_SHADOW PAUSED_RESOURCE {reason}",flush=True)
                continue
            _write_status(
                status="RUNNING",
                experiments=len(specs),
                last_market_minute=str(latest),
                emitted=emitted,
                predictions_total=predictions_total,
                update_seconds=round(elapsed,4),
                rss_mib=round(rss,1),
                fit_calls=runtime.fit_calls,
            )
        except Exception as exc:
            # Research failure must not intentionally bring down production.
            _write_status(
                status="ERROR_BACKOFF",
                error=f"{type(exc).__name__}: {exc}",
            )
            print(f"XS_SHADOW_ERROR {type(exc).__name__}: {exc}",flush=True)
            time.sleep(60)
            continue
        time.sleep(POLL_SECONDS)


if __name__=="__main__":
    main()
