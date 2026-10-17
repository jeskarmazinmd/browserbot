#!/usr/bin/env bash
# From the patched Mac checkout. No broker calls, secret updates, or retirement changes.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "$(git branch --show-current)" != modular-bot || -n "$(git status --porcelain)" ]]; then
  echo 'Commit the reviewed G10 patch on modular-bot with a clean checkout first.' >&2
  exit 1
fi
G10_REVISION="$(git rev-parse HEAD)"
G10_BACKUP="$(mktemp -d "${TMPDIR:-/tmp}/schwab-g10-before.XXXXXX")"
G10_PREFLIGHT="$(python3 research_tools/g8/remote_command.py research_tools/g10/preflight.py)"
fly ssh console -a schwab -C "$G10_PREFLIGHT" | tee "$G10_BACKUP/preflight.json"
fly ssh sftp get -a schwab /data/paper_generation_three_bidask_independent_outcomes.jsonl "$G10_BACKUP/parent-outcomes.jsonl"
fly ssh sftp get -a schwab /data/all_engine_bidask_daily_history.json "$G10_BACKUP/history.json"
fly ssh sftp get -a schwab /data/all_engine_performance_live.json "$G10_BACKUP/performance.json"
python3 -m research_tools.g10.run_checks
# Preserve the established build revision variables used by existing verifiers.
fly deploy -a schwab --strategy immediate \
  --build-arg "G6_BUILD_REVISION=$G10_REVISION" \
  --build-arg "G7_BUILD_REVISION=$G10_REVISION" \
  --build-arg "G8_BUILD_REVISION=$G10_REVISION" \
  --build-arg "G9_BUILD_REVISION=$G10_REVISION" \
  --build-arg "G10_BUILD_REVISION=$G10_REVISION"
fly status -a schwab
fly ssh console -a schwab -C "python -m research_tools.g10.verify_production --expected-revision $G10_REVISION --allow-warmup"
fly ssh console -a schwab -C 'python -m research_tools.g9.verify_production --allow-warmup'
fly ssh console -a schwab -C 'python -m research_tools.g10.audit --parent'
printf 'Baseline evidence: %s\n' "$G10_BACKUP"
printf 'After report refresh: fly ssh console -a schwab -C "python -m research_tools.g10.verify_production --expected-revision %s"\n' "$G10_REVISION"
