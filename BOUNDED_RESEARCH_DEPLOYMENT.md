# Bounded Module Factory research hotfix

This patch changes only historical Factory research preparation and makes the
rolling path full-resolution. Each completed archive is streamed into 32
deterministic symbol buckets. A first pass keeps only global feature-selection
statistics; a second pass stores only the selected ten features plus all
outcomes. One bucket is resident at a time. It does not
alter the quote collector, the legacy three-column tape, existing strategies,
shadow executable pricing, or broker execution controls.

## 1. Keep research disabled while installing

```bash
fly secrets set -a schwab FACTORY_RESEARCH_ENABLED=0
```

## 2. Apply from the repository root

```bash
cd "$HOME/Desktop/browserbot"
patch_zip="$HOME/Downloads/module_factory_bounded_research_20260912.zip"
patch_dir="$(mktemp -d)"
unzip -q "$patch_zip" -d "$patch_dir"

rsync -anv --files-from="$patch_dir/BOUNDED_RESEARCH_MANIFEST.txt" "$patch_dir/" ./
rsync -av --files-from="$patch_dir/BOUNDED_RESEARCH_MANIFEST.txt" "$patch_dir/" ./
cp "$patch_dir/BOUNDED_RESEARCH_DEPLOYMENT.md" ./

.venv/bin/python -m pytest -q \
  research_tools/module_factory/test_bounded_feature_cache.py \
  research_tools/module_factory/test_partitioned_discovery.py \
  research_tools/module_factory/test_distribution_scientist.py \
  research_tools/module_factory/test_regime_scientist.py \
  research_tools/module_factory/test_rolling_controller.py \
  research_tools/module_factory/test_feature_matrix.py

.venv/bin/python -m pytest -q \
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

.venv/bin/python -m compileall -q research_tools/module_factory supervisor.py
git diff --check
```

## 3. Deploy with research still off

```bash
fly deploy -a schwab
fly status -a schwab
fly ssh console -a schwab -C "python -c \"from research_tools.module_factory.bounded_feature_cache import prepare_feature_rows; print('BOUNDED_RESEARCH_IMPORT_OK')\""
```

## 4. Enable a conservative research canary

```bash
fly secrets set -a schwab \
  FACTORY_RESEARCH_ENABLED=1 \
  FACTORY_RESEARCH_STRIDE=1 \
  FACTORY_RESEARCH_MAX_ADDRESS_MB=1536 \
  FACTORY_RESEARCH_CACHE_MAX_MB=512
```

The rolling controller deliberately ignores larger stride values and retains
every eligible minute. Expected checkpoint logs identify `stage=inventory` or
`stage=features`; the latter is the compact durable research partition. Question
logs cover completed/reused feature questions. A restart should report `"reused": true`
for prior checkpoints. Real-money execution remains separately controlled and
must not be enabled for this rollout.

## 5. Verify without relying on the noisy collector log tail

```bash
fly logs -a schwab --no-tail | grep -E \
  'FACTORY_RESEARCH_LIMITS|FACTORY_RESEARCH_CHECKPOINT|FACTORY_RESEARCH_QUESTION|FACTORY_RESEARCH|optional_worker_exit' | tail -n 60

fly ssh console -a schwab -C "python -c \"from pathlib import Path; root=Path('/data/module_factory'); print(chr(10).join(f'{p.relative_to(root)} {p.stat().st_size}' for p in sorted((root/'feature_cache').rglob('*')) if p.is_file()) if (root/'feature_cache').exists() else 'NO_CACHE_YET')\""
```

If the worker returns `DEFERRED_RESOURCES`, leave it enabled: completed archive
checkpoints remain durable and the next scheduled cycle resumes them. If the
512 MB cache budget is exceeded, disable research and inspect before raising
the budget because `/data` free-space protection takes priority.
