#!/usr/bin/env python3
"""Install the research-only C3 exit-duration fan-out with backup."""

from __future__ import annotations

import argparse
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"refusing to patch {label}: expected snippet once, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    source_dir = Path(__file__).resolve().parent

    helper_source = source_dir / "c3_exit_duration_sweep.py"
    test_source = source_dir / "test_c3_exit_duration_sweep.py"
    required = [
        repo / "live_strategy_runner.py",
        repo / "paper_outcome_tracker.py",
        helper_source,
        test_source,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("missing required files:\n" + "\n".join(missing))

    runner = (repo / "live_strategy_runner.py").read_text()
    runner = replace_once(
        runner,
        "from strategies.capacity_filters import apply_capacity_filters\n",
        "from strategies.capacity_filters import apply_capacity_filters\n"
        "from strategies.c3_exit_duration_sweep import derive_duration_signals\n",
        "live_strategy_runner.py import",
    )
    runner = replace_once(
        runner,
        '''                    paper_outcomes.register(e)\n                    if e.get("strategy_id") in parent_signal_counts:''',
        '''                    paper_outcomes.register(e)\n+                    for duration_signal in derive_duration_signals(e):\n+                        append_strategy_event(\n+                            duration_signal["strategy_id"],\n+                            "SIGNAL",\n+                            symbol=duration_signal["symbol"],\n+                            signal=duration_signal,\n+                            signal_regime=latest_regime(),\n+                            thresholds={\n+                                "DERIVED_FROM": "C3N25S10",\n+                                "LIVE_ORDER_PLACEMENT": False,\n+                                "EXIT_MODEL": "c2",\n+                                "NO_NEW_HIGH_SECONDS": duration_signal["no_new_high_seconds"],\n+                                "EXPERIMENT": "c3_nnh_duration_sweep",\n+                            },\n+                        )\n+                        paper_outcomes.register(duration_signal)\n+                    if e.get("strategy_id") in parent_signal_counts:''',
        "live_strategy_runner.py fanout",
    )

    tracker = (repo / "paper_outcome_tracker.py").read_text()
    tracker = replace_once(
        tracker,
        '    "capacity_filter_version",\n)',
        '    "capacity_filter_version",\n'
        '    "exit_duration_sweep_seconds", "exit_duration_sweep_parent",\n'
        '    "exit_duration_sweep_version",\n'
        ')',
        "paper_outcome_tracker.py",
    )

    planned = [
        "strategies/c3_exit_duration_sweep.py",
        "live_strategy_runner.py",
        "paper_outcome_tracker.py",
        "tests/test_c3_exit_duration_sweep.py",
    ]
    print("Validated patch against:", repo)
    for path in planned:
        print(" -", path)
    if not args.apply:
        print("DRY RUN ONLY; rerun with --apply")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = repo / "research_tools" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive = backup_dir / f"pre_c3_exit_duration_sweep_{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for relative in ("live_strategy_runner.py", "paper_outcome_tracker.py"):
            handle.add(repo / relative, arcname=relative)

    shutil.copyfile(helper_source, repo / "strategies/c3_exit_duration_sweep.py")
    shutil.copyfile(test_source, repo / "tests/test_c3_exit_duration_sweep.py")
    (repo / "live_strategy_runner.py").write_text(runner)
    (repo / "paper_outcome_tracker.py").write_text(tracker)
    print("INSTALLED")
    print("BACKUP", archive)


if __name__ == "__main__":
    main()
