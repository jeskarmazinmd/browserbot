"""Read the generation-one executable ledger without resizing fills in hindsight."""
import json
from collections import defaultdict

from generation_one_paper_tracker import FILE_STEM, IDS, spec_for
from paper_outcome_tracker import NY, _utc
from strategies import generation_one as flash, generation_one_minute as minute
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned


def calculate_generation_one(root, day, cutoff, marks, quote_for):
    births_path = root / (FILE_STEM + "_births.json")
    if not births_path.exists():
        return {}, {"entries": 0, "exits": 0, "partial_exits": 0, "rejected": 0, "unmarked": 0}
    births = json.loads(births_path.read_text())
    entries, residuals = {}, {}
    rejects = defaultdict(int)
    diagnostics = {"entries": 0, "exits": 0, "partial_exits": 0, "rejected": 0, "unmarked": 0}
    path = root / (FILE_STEM + "_outcomes.jsonl")
    if path.exists():
        with path.open() as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    sid = row["strategy_id"]
                    signal_time = _utc(row["signal_timestamp"])
                    event = row["event_type"]
                    event_time = _utc(row.get("exit_timestamp") or row.get("entry_timestamp") or row["recorded_at"])
                    valid = (sid in IDS and sid in births and signal_time >= _utc(births[sid])
                             and signal_time.astimezone(NY).date().isoformat() == day
                             and event_time <= cutoff)
                except (KeyError, TypeError, ValueError):
                    continue
                if not valid:
                    continue
                setup = row["setup_id"]
                if event == "PAPER_ENTRY_REJECTED":
                    rejects[sid] += 1
                    diagnostics["rejected"] += 1
                elif event == "PAPER_ENTRY":
                    entries[setup] = row
                    residuals[setup] = row
                    diagnostics["entries"] += 1
                elif event in {"PAPER_PARTIAL_EXIT", "PAPER_EXIT"} and setup in entries:
                    residuals[setup] = row
                    diagnostics["exits" if event == "PAPER_EXIT" else "partial_exits"] += 1
    grouped = defaultdict(list)
    for setup, entry in entries.items():
        grouped[entry["strategy_id"]].append((entry, residuals[setup]))
    modules = {}
    for sid in sorted(IDS):
        if (sid not in births or _utc(births[sid]) > cutoff or
                _utc(births[sid]).astimezone(NY).date().isoformat() > day or
                output_is_pruned(sid) or not output_enabled(sid) or not output_enabled(sid + "BA")):
            continue
        pnl, open_count, closed_count, unmarked = 0.0, 0, 0, 0
        for entry, residual in grouped[sid]:
            remaining = residual["remaining_qty"]
            realized = residual.get("realized_proceeds", 0.0)
            if remaining:
                quote = quote_for(entry["symbol"], marks)
                bid = flash.num(quote.get("bid"))
                if bid <= 0:
                    unmarked += 1
                    continue
                pnl += realized + remaining * bid - entry["notional"]
                open_count += 1
            else:
                pnl += realized - entry["notional"]
                closed_count += 1
        diagnostics["unmarked"] += unmarked
        if unmarked:
            # Never present a partial known subset as a complete portfolio return.
            continue
        equity = getattr(spec_for(sid), "equity", 5000.0)
        metadata = flash.metadata(sid) if sid in flash.IDS else minute.metadata(sid)
        modules[sid + "BA"] = {
            "engine": "generation_one_bidask_independent", "starting_cash": equity,
            "end_equity": equity + pnl, "pnl": pnl, "return_pct": pnl / equity * 100,
            "signals": len(grouped[sid]) + rejects[sid], "taken": len(grouped[sid]),
            "skipped": rejects[sid], "open_taken": open_count, "closed_taken": closed_count,
            "status": "prospective" if grouped[sid] else "no_entries",
            "prospective_start_utc": births[sid], "research_metadata": metadata,
            "portfolio_combinable": False, "actual_fill_quantities": True,
        }
    return modules, diagnostics
