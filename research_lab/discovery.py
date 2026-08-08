"""Automatic strategy and research-data capability discovery."""

from __future__ import annotations

import ast
import csv
import gzip
import json
from pathlib import Path
from typing import Any, Iterable

from research_lab.capabilities import evaluate_capabilities
from research_lab.models import (
    BlindSpot,
    DataSourceSpec,
    DiscoveryReport,
    StrategySpec,
)
from research_lab.provenance import infer_field


def _literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def discover_strategies(repo_root: Path) -> list[StrategySpec]:
    folder = repo_root / "strategies"
    results=[]

    for path in sorted(folder.glob("strategy_*.py")):
        try:
            tree=ast.parse(path.read_text(),filename=str(path))
        except Exception as exc:
            results.append(StrategySpec(
                strategy_id=path.stem.upper(),
                path=path,
                parse_errors=[f"{type(exc).__name__}: {exc}"],
            ))
            continue

        assigned={}
        tags=set()
        class_names=[]

        for node in tree.body:
            if isinstance(node,(ast.Assign,ast.AnnAssign)):
                targets=(
                    node.targets
                    if isinstance(node,ast.Assign)
                    else [node.target]
                )
                value=_literal(node.value)
                for target in targets:
                    if isinstance(target,ast.Name):
                        assigned[target.id]=value

            elif isinstance(node,ast.FunctionDef):
                tags.add(f"function:{node.name}")
                if node.name=="accepts_flash":
                    tags.add("flash_entry")
                if node.name=="metadata":
                    tags.add("metadata")

            elif isinstance(node,ast.ClassDef):
                class_names.append(node.name)
                methods={
                    child.name for child in node.body
                    if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef))
                }
                if "on_snapshot" in methods:
                    tags.add("snapshot_scanner")
                if "evaluate" in methods:
                    tags.add("evaluator")

        sid=str(assigned.get("STRATEGY_ID") or path.stem[9:]).upper()
        config=assigned.get("CONFIG")
        if not isinstance(config,dict):
            config={}

        constants={
            key:value
            for key,value in assigned.items()
            if key.isupper() and value is not None
        }

        family=assigned.get("FAMILY")
        paper=assigned.get("PAPER_ONLY")

        if class_names:
            tags.add("classes:" + ",".join(class_names))

        results.append(StrategySpec(
            strategy_id=sid,
            path=path,
            family=str(family or ""),
            paper_only=paper if isinstance(paper,bool) else None,
            config=config,
            constants=constants,
            structural_tags=tags,
        ))

    return results


def _flatten(value: Any, prefix="") -> set[str]:
    fields=set()

    if isinstance(value,dict):
        for key,child in value.items():
            name=f"{prefix}.{key}" if prefix else str(key)
            fields.add(name)
            fields.update(_flatten(child,name))

    elif isinstance(value,list):
        name=f"{prefix}[]" if prefix else "[]"
        fields.add(name)
        for child in value[:3]:
            fields.update(_flatten(child,name))

    return fields


def _roles(path: Path) -> set[str]:
    name=path.name.lower()
    roles=set()

    patterns={
        "capital_performance": ("capital_constrained","capital_performance"),
        "paper_outcome": ("paper_signal_outcomes","paper_outcomes"),
        "research_outcome": ("signal_paper_outcomes","research"),
        "near_miss": ("near_miss",),
        "regime": ("regime",),
        "resource": ("resource_",),
        "minute_market_data": ("minute_quote","minute_cache"),
        "quote_tape": ("quotes_","quote_tape","tape"),
        "diagnostics": ("diagnostic",),
    }

    for role,needles in patterns.items():
        if any(x in name for x in needles):
            roles.add(role)

    return roles or {"unclassified"}


def _jsonl_records(path: Path, limit: int | None) -> Iterable[dict]:
    opener=gzip.open if path.suffix==".gz" else open
    count=0

    with opener(path,"rt",errors="replace") as handle:
        for line in handle:
            if limit is not None and count>=limit:
                break
            try:
                row=json.loads(line)
            except Exception:
                continue
            count+=1
            if isinstance(row,dict):
                yield row


def inspect_source(
    path: Path,
    schema_mode: str="sample",
    sample_records: int=2000,
) -> DataSourceSpec:
    suffixes="".join(path.suffixes).lower()
    fmt="unknown"
    fields=set()
    sampled=0
    notes=[]

    try:
        size=path.stat().st_size
    except OSError:
        size=0

    limit=None if schema_mode=="full" else sample_records

    try:
        if suffixes.endswith(".jsonl") or suffixes.endswith(".jsonl.gz"):
            fmt="jsonl.gz" if suffixes.endswith(".gz") else "jsonl"
            for row in _jsonl_records(path,limit):
                sampled+=1
                fields.update(_flatten(row))

        elif path.suffix.lower()==".json":
            fmt="json"
            value=json.loads(path.read_text())
            sampled=1
            fields.update(_flatten(value))

        elif path.suffix.lower()==".csv":
            fmt="csv"
            with path.open(newline="",errors="replace") as handle:
                reader=csv.reader(handle)
                header=next(reader,[])
            fields.update(str(x) for x in header)
            sampled=1 if header else 0

        elif path.suffix.lower() in {".pkl",".pickle"}:
            fmt="pickle"
            notes.append(
                "opaque pickle intentionally not deserialized by generic discovery"
            )

        elif path.suffix.lower()==".txt":
            fmt="text"

    except Exception as exc:
        notes.append(f"inspection error: {type(exc).__name__}: {exc}")

    return DataSourceSpec(
        path=path,
        format=fmt,
        size_bytes=size,
        roles=_roles(path),
        fields=fields,
        records_sampled=sampled,
        notes=notes,
    )


def discover_sources(
    data_root: Path,
    schema_mode: str="sample",
    sample_records: int=2000,
) -> list[DataSourceSpec]:
    if not data_root.exists():
        return []

    supported={".json",".jsonl",".gz",".csv",".pkl",".pickle",".txt"}
    results=[]

    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in supported:
            continue
        results.append(inspect_source(path,schema_mode,sample_records))

    return results


def build_report(
    repo_root: Path,
    data_root: Path,
    schema_mode: str="sample",
    sample_records: int=2000,
) -> DiscoveryReport:
    strategies=discover_strategies(repo_root)
    sources=discover_sources(data_root,schema_mode,sample_records)

    all_fields=sorted({
        field
        for source in sources
        for field in source.fields
    })
    provenance=[infer_field(field) for field in all_fields]
    capabilities=evaluate_capabilities(
        strategies,
        sources,
        provenance,
    )

    blind=[]

    roles=set().union(*(s.roles for s in sources)) if sources else set()

    required_roles={
        "paper_outcome": "No paper outcome ledger discovered.",
        "capital_performance": "No finite-capital history discovered.",
        "near_miss": "No near-miss dataset discovered; loosening filters may be untestable.",
        "regime": "No regime history discovered.",
        "minute_market_data": "No minute market dataset discovered for replay.",
    }

    for role,message in required_roles.items():
        if role not in roles:
            blind.append(BlindSpot("missing_data",message,"WARN"))

    if any(s.format=="pickle" for s in sources):
        blind.append(BlindSpot(
            "opaque_data",
            "Pickle datasets were catalogued but not generically inspected.",
            "INFO",
        ))

    unknown=sum(
        1 for x in provenance
        if x.temporal_class.value=="UNKNOWN"
    )
    if unknown:
        blind.append(BlindSpot(
            "provenance",
            f"{unknown} discovered field paths have UNKNOWN temporal provenance.",
            "WARN",
        ))

    parse_errors=sum(bool(s.parse_errors) for s in strategies)
    if parse_errors:
        blind.append(BlindSpot(
            "strategy_source",
            f"{parse_errors} strategy modules could not be parsed cleanly.",
            "WARN",
        ))

    return DiscoveryReport(
        strategies=strategies,
        sources=sources,
        provenance=provenance,
        capabilities=capabilities,
        blind_spots=blind,
    )
