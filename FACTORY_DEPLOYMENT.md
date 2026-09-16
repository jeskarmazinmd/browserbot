# Autonomous Module Factory deployment

This patch is paper-only. `LIVE_ELIGIBLE` is a Factory registry state and does
not modify the production strategy registry, `LIVE_STRATEGY_ID`, or live order
placement settings.

## Patch contents

- Executable bid/ask archive reader with strict timestamp, side, spread, and
  age validation; no last-price fallback.
- Fsync-backed signal journal plus idempotent journal-offset reconciliation.
- Durable executable outcome tracking and incremental lifecycle aggregation.
- Autonomous WATCH, DISABLED, PROSPECTIVE_PASS, and LIVE_ELIGIBLE decisions.
- Automatic best-candidate refill under bounded/adaptive capacity.
- Generic data-only causal compiler for future scientist output.
- Unit and end-to-end coverage for the autonomous loop.

## Apply and test locally

Run from the root of the real bot repository. Preserve unrelated dirty files.

```bash
git status --short
unzip -l autonomous_module_factory_patch_20260911.zip
patch_dir="$(mktemp -d)"
unzip -q autonomous_module_factory_patch_20260911.zip -d "$patch_dir"
rsync -anv --files-from="$patch_dir/PATCH_MANIFEST.txt" "$patch_dir/" ./
rsync -av --files-from="$patch_dir/PATCH_MANIFEST.txt" "$patch_dir/" ./
python3 -m pytest -q \
  research_tools/module_factory/test_executable_quote_feed.py \
  research_tools/module_factory/test_prospective_tracker.py \
  research_tools/module_factory/test_shadow_lifecycle.py \
  research_tools/module_factory/test_population_manager.py \
  research_tools/module_factory/test_factory_shadow_worker.py \
  research_tools/module_factory/test_factory_worker_backlog.py \
  research_tools/module_factory/test_factory_worker_governor.py \
  research_tools/module_factory/test_module_registry.py \
  research_tools/module_factory/test_generated_loader.py \
  research_tools/module_factory/test_generated_strategy.py \
  research_tools/module_factory/test_generated_expression_runtime.py \
  research_tools/module_factory/test_shadow_runtime.py \
  research_tools/module_factory/test_supervisor_integration.py \
  research_tools/module_factory/test_adaptive_capacity.py \
  research_tools/module_factory/test_causal_compiler.py \
  research_tools/module_factory/test_autonomous_factory_e2e.py
python3 -m compileall -q research_tools/module_factory supervisor.py
git diff --check
git diff -- research_tools/module_factory supervisor.py Dockerfile
```

The handoff ZIP does not contain `research_tools/cascade_reversal_study.py`.
Run the repository's complete test suite only in the real checkout where that
existing dependency is present:

```bash
python3 -m pytest -q
```

## Staged Fly deployment

Deploy code first with all Factory workers disabled:

```bash
fly deploy -a schwab
fly ssh console -a schwab -C 'python -m compileall -q /app/research_tools/module_factory'
fly logs -a schwab
```

Enable only the bounded paper shadow worker initially:

```bash
fly secrets set -a schwab \
  FACTORY_SHADOW_ENABLED=1 \
  FACTORY_RESEARCH_ENABLED=0 \
  FACTORY_LITERATURE_ENABLED=0 \
  FACTORY_MAX_SHADOW_MODULES=16 \
  FACTORY_MAX_SIGNALS_PER_CYCLE=50 \
  FACTORY_MAX_MINUTES_PER_CYCLE=2 \
  FACTORY_HISTORY_MINUTES=75 \
  FACTORY_MAX_QUOTE_AGE_SECONDS=90 \
  FACTORY_MIN_MEMORY_AVAILABLE_MB=1024 \
  FACTORY_MIN_DATA_FREE_MB=1024 \
  FACTORY_MAX_LOAD_PER_CPU=1.25
```

Verify paper-only status, archive freshness, reconciliation, and health:

```bash
fly ssh console -a schwab -C 'python - <<"PY"
import json
from pathlib import Path
root = Path("/data/module_factory")
health = json.loads((root / "health.json").read_text())
assert health["paper_only"] is True
assert health["broker_execution_enabled"] is False
assert health["execution_model"] == "BIDASK_EXEC_V1"
print(json.dumps(health, indent=2, sort_keys=True))
for name in ("shadow_signals.jsonl", "bidask_outcomes.jsonl", "bidask_outcomes.aggregate.json"):
    path = root / name
    print(name, path.exists(), path.stat().st_size if path.exists() else 0)
PY'
fly ssh console -a schwab -C 'tail -n 30 /data/worker_supervisor.jsonl'
fly logs -a schwab
```

After at least one stable market session, enable autonomous after-hours
discovery/validation. Literature ingestion can remain separately disabled:

```bash
fly secrets set -a schwab FACTORY_RESEARCH_ENABLED=1
```

Rollback is non-destructive and leaves research evidence intact:

```bash
fly secrets set -a schwab \
  FACTORY_SHADOW_ENABLED=0 \
  FACTORY_RESEARCH_ENABLED=0 \
  FACTORY_LITERATURE_ENABLED=0
```

Do not set or alter `LIVE_ORDER_PLACEMENT_ENABLED` as part of this rollout.
