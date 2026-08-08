"""Compute-only benchmark for adaptive XS relationship fitting.

Historical/after-hours minute caches may be used here to measure CPU and
memory shape.  Results from this module are NEVER trading-performance evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import gc
from pathlib import Path
import resource
import statistics
import sys
import time

import pandas as pd

from research_lab.xs_adaptive import AdaptiveXSConfig, _fit_statistics


COMPUTE_ONLY="COMPUTE_ONLY_NOT_TRADING_EVIDENCE"


@dataclass(frozen=True)
class XSBenchmarkResult:
    role: str
    source: str
    minutes: int
    symbols: int
    complete_symbols: int
    repeats: int
    median_fit_seconds: float
    min_fit_seconds: float
    max_fit_seconds: float
    process_peak_rss_mib: float
    dense_matrix_mib: float


def _rss_mib():
    value=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    return value/(1024**2) if sys.platform=="darwin" else value/1024.0


def load_minute_cache(path):
    """Load only the bot's trusted local minute-cache schema."""
    path=Path(path)
    frame=pd.read_pickle(path)
    required={"timestamp","symbol","price"}
    if not isinstance(frame,pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError("unexpected minute-cache schema")
    work=frame[["timestamp","symbol","price"]].copy()
    work["timestamp"]=pd.to_datetime(work["timestamp"],errors="coerce",utc=True)
    work["price"]=pd.to_numeric(work["price"],errors="coerce")
    work=work.dropna(subset=["timestamp","symbol","price"])
    return work


def benchmark_minute_cache(path, *, lookback=60, horizon=1, repeats=3):
    """Time one dense causal relationship fit repeatedly on real-shaped data."""
    frame=load_minute_cache(path)
    wide=frame.pivot_table(
        index="timestamp",columns="symbol",values="price",aggfunc="last"
    ).sort_index()
    if len(wide) < int(lookback)+int(horizon)+2:
        raise ValueError("cache does not contain enough minute rows for benchmark")

    decision_pos=len(wide)-1
    config=AdaptiveXSConfig(
        lookback_minutes=int(lookback),
        horizon_minutes=int(horizon),
        refresh_minutes=5,
        min_observations=min(30,int(lookback)-5),
    )

    times=[]
    complete=0
    for _ in range(max(1,int(repeats))):
        gc.collect()
        start=time.perf_counter()
        stats=_fit_statistics(wide,decision_pos,config)
        times.append(time.perf_counter()-start)
        complete=0 if stats is None else len(stats["names"])
        del stats

    n=wide.shape[1]
    return XSBenchmarkResult(
        role=COMPUTE_ONLY,
        source=str(Path(path)),
        minutes=len(wide),
        symbols=n,
        complete_symbols=complete,
        repeats=len(times),
        median_fit_seconds=float(statistics.median(times)),
        min_fit_seconds=float(min(times)),
        max_fit_seconds=float(max(times)),
        process_peak_rss_mib=_rss_mib(),
        dense_matrix_mib=(n*n*8)/(1024**2),
    )


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("cache")
    parser.add_argument("--lookback",type=int,default=60)
    parser.add_argument("--horizon",type=int,default=1)
    parser.add_argument("--repeats",type=int,default=3)
    args=parser.parse_args(argv)
    result=benchmark_minute_cache(
        args.cache,
        lookback=args.lookback,
        horizon=args.horizon,
        repeats=args.repeats,
    )
    print("XS COMPUTE BENCHMARK")
    for name,value in result.__dict__.items():
        print(f"{name:24} {value}")


if __name__=="__main__":
    main()
