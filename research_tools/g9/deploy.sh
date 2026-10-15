#!/usr/bin/env bash
# Run locally after pulling the reviewed commit. First production operation is read-only SSH.
set -euo pipefail
cd "$(dirname "$0")/../.."
G9_REVISION="$(git rev-parse HEAD)"
G9_PYTHON="${G9_PYTHON:-python3}"
G9_BACKUP="$(mktemp -d "${TMPDIR:-/tmp}/schwab-g9-before.XXXXXX")"
if [[ "$(git branch --show-current)" != modular-bot || -n "$(git status --porcelain)" ]]; then
  echo 'Use a clean modular-bot checkout.' >&2; exit 1
fi
G9_PREFLIGHT="$("$G9_PYTHON" research_tools/g8/remote_command.py research_tools/g9/preflight.py)"
fly ssh console -a schwab -C "$G9_PREFLIGHT" | tee "$G9_BACKUP/preflight.json"
fly ssh sftp get -a schwab /data/statarb_paper_outcomes.jsonl "$G9_BACKUP/statarb_paper_outcomes.jsonl"
fly ssh sftp get -a schwab /data/all_engine_bidask_daily_history.json "$G9_BACKUP/all_engine_bidask_daily_history.json"
fly ssh sftp get -a schwab /data/all_engine_performance_live.json "$G9_BACKUP/all_engine_performance_live.json"
echo "Pre-deployment evidence saved: $G9_BACKUP"
"$G9_PYTHON" -m unittest tests.test_generation_nine tests.test_statarb2 tests.test_all_engine_performance -q
fly deploy -a schwab --strategy immediate --build-arg "G6_BUILD_REVISION=$G9_REVISION" --build-arg "G7_BUILD_REVISION=$G9_REVISION" --build-arg "G8_BUILD_REVISION=$G9_REVISION" --build-arg "G9_BUILD_REVISION=$G9_REVISION"
fly status -a schwab
fly ssh console -a schwab -C 'python -m research_tools.g9.verify_production --allow-warmup'
fly ssh console -a schwab -C 'python -m research_tools.g9.parent_audit'
echo "After the next report refresh: fly ssh console -a schwab -C 'python -m research_tools.g9.verify_production'"
echo "Active terminal table: fly ssh console -a schwab -C 'python -m research_tools.g9.performance_table --days 5'"
