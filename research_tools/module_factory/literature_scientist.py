"""Bounded after-hours retrieval of external research inspiration.

Retrieved material is provenance-bearing inspiration, never empirical evidence.
This process is separate from the live Factory shadow worker.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from research_tools.module_factory.idea_library import IdeaLibrary
from research_tools.module_factory.knowledge_corpus import KnowledgeCorpus
from research_tools.module_factory.knowledge_ingestion import (
    KnowledgeDocument,
    ingest_documents,
)
from research_tools.module_factory.resource_governor import ResourceGovernor


DEFAULT_QUERIES = (
    "intraday stock return predictability market microstructure",
    "cross sectional momentum reversal intraday equities",
    "bid ask spread liquidity short horizon return prediction",
)


def reconstruct_abstract(index: dict | None) -> str:
    if not isinstance(index, dict):
        return ""
    positioned = []
    for word, positions in index.items():
        for position in positions or ():
            try:
                positioned.append((int(position), str(word)))
            except (TypeError, ValueError):
                continue
    return " ".join(word for _, word in sorted(positioned))


class OpenAlexLiteratureSource:
    endpoint = "https://api.openalex.org/works"

    def __init__(self, *, mailto: str = "", timeout_seconds: float = 20.0):
        self.mailto = mailto.strip()
        self.timeout_seconds = float(timeout_seconds)

    def search(self, query: str, *, limit: int = 10) -> list[KnowledgeDocument]:
        params = {
            "search": query,
            "filter": "type:article|preprint",
            "sort": "cited_by_count:desc",
            "per-page": str(max(1, min(int(limit), 25))),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        request = Request(
            self.endpoint + "?" + urlencode(params),
            headers={"User-Agent": "browserbot-module-factory/1.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        documents = []
        for work in payload.get("results", []):
            title = str(work.get("display_name") or "").strip()
            abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
            if not title or not abstract:
                continue
            authors = tuple(
                str(item.get("author", {}).get("display_name"))
                for item in work.get("authorships", [])[:12]
                if item.get("author", {}).get("display_name")
            )
            locator = str((work.get("primary_location") or {}).get("landing_page_url") or work.get("doi") or work.get("id") or "")
            documents.append(KnowledgeDocument(
                source_type="academic", title=title, text=abstract,
                authors=authors, year=work.get("publication_year"),
                locator=locator, stance="neutral",
                tags=("external_search", "openalex", query),
                metadata={
                    "openalex_id": work.get("id"),
                    "doi": work.get("doi"),
                    "cited_by_count": work.get("cited_by_count"),
                    "retrieval_query": query,
                },
            ))
        return documents


def after_market_hours(now: datetime | None = None) -> bool:
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return local.weekday() >= 5 or local.hour >= 17 or local.hour < 8


def run_once(
    *, data_root: Path = Path("/data"), queries=DEFAULT_QUERIES,
    results_per_query: int = 10, force: bool = False,
    source: OpenAlexLiteratureSource | None = None,
    resource_governor: ResourceGovernor | None = None,
) -> dict:
    root = Path(data_root) / "module_factory"
    status_path = root / "literature_status.json"
    if not force and not after_market_hours():
        result = {"status": "DEFERRED_MARKET_HOURS", "documents_added": 0, "ideas_added": 0}
    else:
        governor = resource_governor or ResourceGovernor(
            min_memory_available_mb=float(os.getenv("FACTORY_MIN_MEMORY_AVAILABLE_MB", "1024")),
            min_data_free_mb=float(os.getenv("FACTORY_MIN_DATA_FREE_MB", "1024")),
            max_load_per_cpu=float(os.getenv("FACTORY_MAX_LOAD_PER_CPU", "1.25")),
        )
        decision = governor.check(data_root=Path(data_root))
        if not decision.allowed:
            result = {"status": "DEFERRED_RESOURCES", "reasons": decision.reasons, "documents_added": 0, "ideas_added": 0}
        else:
            source = source or OpenAlexLiteratureSource(mailto=os.getenv("FACTORY_LITERATURE_MAILTO", ""))
            documents = []
            errors = []
            for query in tuple(queries)[:5]:
                try:
                    documents.extend(source.search(str(query), limit=results_per_query))
                except Exception as exc:
                    errors.append({"query": str(query), "error": type(exc).__name__ + ": " + str(exc)})
            corpus = KnowledgeCorpus(root / "knowledge_corpus.jsonl")
            library = IdeaLibrary(root / "idea_library.jsonl")
            added = corpus.add_many(documents, retrieval_method="openalex_api")
            records = ingest_documents(library, documents)
            result = {
                "status": "OK" if not errors else "PARTIAL",
                "documents_retrieved": len(documents), "documents_added": added,
                "ideas_added": len(records), "errors": errors,
                "boundary": "INSPIRATION_ONLY_NOT_EVIDENCE",
            }
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    root.mkdir(parents=True, exist_ok=True)
    temporary = status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(status_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/data")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--results-per-query", type=int, default=10)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=21600)
    args = parser.parse_args()
    while True:
        print(json.dumps(run_once(
            data_root=Path(args.data_root), force=args.force,
            results_per_query=args.results_per_query,
        ), sort_keys=True), flush=True)
        if not args.loop:
            break
        time.sleep(max(3600.0, args.interval_seconds))


if __name__ == "__main__":
    main()
