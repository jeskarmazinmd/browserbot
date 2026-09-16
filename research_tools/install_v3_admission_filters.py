#!/usr/bin/env python3
"""Install prospective research-only admission gates with a local backup."""

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

    targets = {
        "strategies/capacity_filters.py": source_dir / "capacity_filters_prospective.py",
        "tests/test_capacity_filters_prospective.py": source_dir / "test_capacity_filters_prospective.py",
    }
    required = [
        repo / "live_strategy_runner.py",
        repo / "paper_outcome_tracker.py",
        repo / "tests/test_capacity_filters.py",
        targets["strategies/capacity_filters.py"],
        targets["tests/test_capacity_filters_prospective.py"],
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("missing required files:\n" + "\n".join(missing))

    runner = (repo / "live_strategy_runner.py").read_text()
    runner = replace_once(
        runner,
        '''                minute_payloads = apply_capacity_filters([\n                    snapshot_signal_payload(signal)\n                    for signal in single_leg_signals\n                ])''',
        '''                minute_payloads = apply_capacity_filters(\n                    [\n                        snapshot_signal_payload(signal)\n                        for signal in single_leg_signals\n                    ],\n                    regime=latest_regime(),\n                )''',
        "live_strategy_runner.py",
    )

    tracker = (repo / "paper_outcome_tracker.py").read_text()
    tracker = replace_once(
        tracker,
        '    "last_observed_price", "last_observed_at",\n    "breakeven_after_activation",',
        '    "last_observed_price", "last_observed_at",\n'
        '    "breakeven_after_activation",\n'
        '    "capacity_filter_passed", "capacity_filter_audit",\n'
        '    "capacity_filter_version",',
        "paper_outcome_tracker.py",
    )

    old_tests = (repo / "tests/test_capacity_filters.py").read_text()
    old_tests = replace_once(
        old_tests,
        "self.assertEqual(22, len(CAPACITY_FILTERS))",
        "self.assertEqual(31, len(CAPACITY_FILTERS))",
        "tests/test_capacity_filters.py inventory",
    )
    old_tests = replace_once(
        old_tests,
        'payload = self.payload("AV1", "AAA")',
        'payload = self.payload("PTD1X", "AAA")',
        "tests/test_capacity_filters.py passthrough",
    )

    planned = [
        "strategies/capacity_filters.py",
        "live_strategy_runner.py",
        "paper_outcome_tracker.py",
        "tests/test_capacity_filters.py",
        "tests/test_capacity_filters_prospective.py",
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
    archive = backup_dir / f"pre_v3_admission_filters_{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for relative in planned[:-1]:
            path = repo / relative
            if path.exists():
                handle.add(path, arcname=relative)

    shutil.copyfile(targets["strategies/capacity_filters.py"], repo / "strategies/capacity_filters.py")
    (repo / "live_strategy_runner.py").write_text(runner)
    (repo / "paper_outcome_tracker.py").write_text(tracker)
    (repo / "tests/test_capacity_filters.py").write_text(old_tests)
    shutil.copyfile(
        targets["tests/test_capacity_filters_prospective.py"],
        repo / "tests/test_capacity_filters_prospective.py",
    )
    print("INSTALLED")
    print("BACKUP", archive)


if __name__ == "__main__":
    main()
