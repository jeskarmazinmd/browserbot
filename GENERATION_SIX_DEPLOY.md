# Apply and deploy the reviewed G6 patch

The patch assumes the modular-bot checkout at cf7b7f77 plus the evidence-export patch and missing-git hotfix already applied. It preserves that work. Do not proceed if git apply --check fails; share its output so we can reconcile your checkout.

Download g6_400_modules.patch to Downloads, then:

```bash
cd ~/Desktop/browserbot
git status --short
git apply --check ~/Downloads/g6_400_modules.patch
git apply ~/Downloads/g6_400_modules.patch
python3 -m research_tools.g6.run_checks
python3 -m benchmarks.benchmark_generation_six
git diff --stat
```

Expected checks: 197 passing tests; benchmark accepts 400 modules. The old microstructure10 definition-count assertion also fails before this patch and remains unchanged. Review research/g6/RESEARCH_REPORT.md and GENERATION_SIX_RETIREMENT.json. No G6 trade is backfilled; all 400 durable starts are created on activation. The October 9 report cutoff precedes these births and may show zero G6 rows; tracker status verifies the population independently.

Before committing, review all local changes. The next command stages the G6 files and the earlier evidence-export files by explicit path. If you have unrelated edits within those same files, separate them before committing. It does not stage other paths.

```bash
git add -- Dockerfile GENERATION_SIX_DEPLOY.md GENERATION_SIX_RETIREMENT.json GENERATION_SIX_RUNTIME_HASHES.json benchmarks/benchmark_generation_six.py bidask_multi_leg_paper_tracker.py bidask_paper_outcome_tracker.py fly.toml forex_paper_tracker.py generation_six_paper_tracker.py live_strategy_runner.py microstructure_paper_tracker.py multi_leg_paper_tracker.py paper_outcome_tracker.py reporting/all_engine_performance.py reporting/generation_six_performance.py research/g6/RESEARCH_REPORT.md research/g6/benchmark.json research/g6/parent_audit.json research/g6/population.json research/g6/validation.json research_tools/g6/agreed_ranking_ids.json research_tools/g6/analyze_evidence.py research_tools/g6/collect_from_fly.py research_tools/g6/export_evidence.py research_tools/g6/run_checks.py research_tools/g6/supplement_audit.py research_tools/g6/verify_production.py short_paper_tracker.py statarb_paper_tracker.py strategies/generation_six.py strategies/generation_six_retirement.py strategies/pruning.py strategies/registry.py strategies/research_retirement.py tests/test_g6_evidence_export.py tests/test_generation_six.py
```

```bash
git diff --cached --stat
git commit -m "Add 400 prospective G6 paper experiments and exact ranking retirement"
git push origin modular-bot
fly deploy -a schwab --build-arg G6_BUILD_REVISION="$(git rev-parse HEAD)"
```

Deployment uses fly.toml's ENABLE_G6_PAPER=1. The reviewed live-order flag remains 0; the existing disabled broker function is unchanged. Verify after the runner and performance reporter refresh:

```bash
fly ssh console -a schwab --machine 7813422f149398 -C "python -m research_tools.g6.verify_production --expected-revision $(git rev-parse HEAD)"
```

Expected audit: errors=[], exactly 400 G6 registrations/births, 240 flash and 160 minute, exactly 400 frozen retired outputs, no retired active output, matching deployed source and git revision, paper safeguards and required processes. Latest report row counts are cutoff-dependent. The audit reports main-registry and native-worker counts separately; it does not label a historical ranking count as a global process count. If the machine ID changes during deployment, use the current machine ID from fly machine list -a schwab. Inspect production resource utilization and fresh quote/observation progress before interpreting research results; the local benchmark excludes network and worker IPC.

Rollback: change ENABLE_G6_PAPER to "0" in fly.toml, commit and deploy that configuration. Preserve /data G6 files. That stops new G6 admissions and reverses this selection retirement; the runner keeps recovering existing G6 positions for exits. Do not edit frozen G6 rules under existing IDs or delete births/ledgers to restart results.
