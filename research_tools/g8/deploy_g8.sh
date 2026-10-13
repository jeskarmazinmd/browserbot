#!/usr/bin/env bash
# User-approved G8 workflow. No secrets changed; never suppress a failed check.
set -euo pipefail
G8_DELIVERY_DIR="$(cd "$(dirname "$0")" && pwd)"
G8_REPO="${G8_REPO:-$HOME/Desktop/browserbot}"
G8_BASE="fc22309f399dfb089e135022dc96b0c5abd2e3ee"
G8_TARGET="$(cat "$G8_DELIVERY_DIR/TARGET_COMMIT")"
G8_MACHINE="7813422f149398"
G8_LOG_DIR="$G8_DELIVERY_DIR/logs"
mkdir -p "$G8_LOG_DIR"
command -v fly >/dev/null
command -v git >/dev/null
G8_PYTHON="${G8_PYTHON:-python3}"
if [[ -x "$G8_REPO/.venv/bin/python" && "$G8_PYTHON" == python3 ]]; then G8_PYTHON="$G8_REPO/.venv/bin/python"; fi
"$G8_PYTHON" -c 'import numpy,pandas'

# Execute the stdlib-only inspector in memory on the currently deployed build.
# This is the first production operation; it does not write or restart anything.
G8_PREFLIGHT_COMMAND="$("$G8_PYTHON" "$G8_DELIVERY_DIR/remote_command.py" "$G8_DELIVERY_DIR/preflight.py" --expected-revision "$G8_BASE,$G8_TARGET")"
fly ssh console -a schwab --machine "$G8_MACHINE" -C "$G8_PREFLIGHT_COMMAND" | tee "$G8_LOG_DIR/preflight.json"

cd "$G8_REPO"
if [[ "$(git branch --show-current)" != modular-bot ]]; then echo 'Use the modular-bot branch before running this delivery.' >&2; exit 1; fi
if [[ -n "$(git status --porcelain)" ]]; then echo 'Repository has local changes; preserve/commit them before applying G8.' >&2; exit 1; fi
git fetch origin modular-bot
G8_LOCAL_HEAD="$(git rev-parse HEAD)"
G8_REMOTE_HEAD="$(git rev-parse origin/modular-bot)"
if [[ ( "$G8_LOCAL_HEAD" != "$G8_BASE" && "$G8_LOCAL_HEAD" != "$G8_TARGET" ) || ( "$G8_REMOTE_HEAD" != "$G8_BASE" && "$G8_REMOTE_HEAD" != "$G8_TARGET" ) ]]; then
  echo 'Baseline changed; stop for a reviewed merge instead of overwriting newer work.' >&2; exit 1
fi
git bundle verify "$G8_DELIVERY_DIR/g8_changes.bundle"
git fetch "$G8_DELIVERY_DIR/g8_changes.bundle" g8-approved
if [[ "$(git rev-parse FETCH_HEAD)" != "$G8_TARGET" ]]; then echo 'Bundle commit does not match delivery.' >&2; exit 1; fi

# Test before touching the working modular-bot checkout.
G8_CHECKOUT="$(mktemp -d "${TMPDIR:-/tmp}/schwab-g8-check.XXXXXX")"
git worktree add --detach "$G8_CHECKOUT" "$G8_TARGET"
echo "Testing isolated checkout: $G8_CHECKOUT"
(cd "$G8_CHECKOUT" && "$G8_PYTHON" -m research_tools.g8.run_checks) 2>&1 | tee "$G8_LOG_DIR/local_checks.txt"
git worktree remove "$G8_CHECKOUT"

# The bundle carries the reviewed Git commit; fast-forward preserves its audit trail.
git merge --ff-only "$G8_TARGET"
git push origin modular-bot

if "$G8_PYTHON" "$G8_DELIVERY_DIR/already_deployed.py" "$G8_LOG_DIR/preflight.json" "$G8_TARGET"; then
  fly ssh console -a schwab --machine "$G8_MACHINE" -C "python -m research_tools.g8.verify_production --expected-revision $G8_TARGET --allow-warmup" | tee "$G8_LOG_DIR/production_verification.json"
  echo 'This exact G8 build is already deployed; verification completed without redeployment.'
  exit 0
fi

# Assess again immediately before the approved preservation/deployment phase.
fly ssh console -a schwab --machine "$G8_MACHINE" -C "$G8_PREFLIGHT_COMMAND" | tee "$G8_LOG_DIR/predeploy_preflight.json"
G8_PRESERVE_COMMAND="$("$G8_PYTHON" "$G8_DELIVERY_DIR/remote_command.py" "$G8_DELIVERY_DIR/preserve.py")"
fly ssh console -a schwab --machine "$G8_MACHINE" -C "$G8_PRESERVE_COMMAND" | tee "$G8_LOG_DIR/preservation.json"
fly ssh sftp get -a schwab /data/g8_preservation_latest.zip "$G8_DELIVERY_DIR/production_before_G8.zip"
"$G8_PYTHON" -c 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; assert "preservation_manifest.json" in z.namelist(); print("Production backup ZIP verified")' "$G8_DELIVERY_DIR/production_before_G8.zip"

# Single-machine update; G8 writer lock and durable recovery prevent duplicate accounts.
fly deploy -a schwab --strategy immediate --build-arg "G6_BUILD_REVISION=$G8_TARGET" --build-arg "G7_BUILD_REVISION=$G8_TARGET" --build-arg "G8_BUILD_REVISION=$G8_TARGET" 2>&1 | tee "$G8_LOG_DIR/deploy.txt"
fly status -a schwab | tee "$G8_LOG_DIR/fly_status.txt"
if ! fly ssh console -a schwab --machine "$G8_MACHINE" -C "python -m research_tools.g8.verify_production --expected-revision $G8_TARGET --allow-warmup" | tee "$G8_LOG_DIR/production_verification.json"; then
  echo 'Production verification failed. Stopping new G8 entries; retain compatible residual exits and approved retirement gates.' >&2
  fly secrets set ENABLE_G8_PAPER=0 -a schwab
  exit 1
fi
fly ssh console -a schwab --machine "$G8_MACHINE" -C 'python -m research_tools.g8.performance_table --last-finalized 4' | tee "$G8_LOG_DIR/performance_table.txt"
echo "G8 deployed and structural checks passed. Review pending warmup/report-refresh items in $G8_LOG_DIR/production_verification.json."
echo "Next market-session check: fly ssh console -a schwab --machine $G8_MACHINE -C 'python -m research_tools.g8.verify_production --expected-revision $G8_TARGET'"
