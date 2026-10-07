# G4 deployment and verification

This change has been locally implemented and tested. It has **not** been deployed by this workspace. Use the authenticated Mac/Fly environment that normally deploys `schwab`. Do not copy production credentials into a patch, source bundle or chat.

## 1. Check production through SSH first

From the Mac terminal:

```bash
fly ssh console -a schwab
```

At `root@...:/app#`:

```bash
python - <<'PY'
import json,os
from pathlib import Path
from strategies import registry,generation_three as g3
print('G3 flag:',os.getenv('ENABLE_G3_PAPER'))
print('G3 flash/minute:',len(g3.IDS & registry.flash_strategy_configs().keys()),sum(s.name in g3.MINUTE_IDS for s in registry.MINUTE_STRATEGIES))
print('strategy failures:',registry.FAILED_STRATEGIES)
print('paper broker entry function is disabled in the source: verify before deployment')
for stem in ['one','two','three']:
 p=Path('/data')/f'paper_generation_{stem}_bidask_independent_status.json'
 print(stem,json.loads(p.read_text()) if p.exists() else 'missing')
PY
ps -eo pid,pcpu,pmem,rss,etime,args --sort=-pcpu | head -20
free -h
df -h /data
exit
```

## 2. Apply the tested patch on the Mac

The patch is based on commit `0af3a25a7d98ee64d849c0f39f3060ac0d165b4f`. Use the normal `modular-bot` checkout. Preserve unrelated local work; if the checkout differs or the patch check fails, reconcile the differences before deploying.

```bash
cd ~/Desktop/browserbot
git branch --show-current
git status --short
git log -1 --oneline
git apply --check ~/Downloads/generation_four.patch
git apply ~/Downloads/generation_four.patch
python -m unittest discover -s tests -p 'test_generation_*.py'
python benchmarks/benchmark_generation_four.py
git diff --check
```

The research report explains the known baseline full-suite failures. The dedicated generation tests must pass. Do not call a baseline failure evidence that a newly failing G4 test is acceptable.

Stage the G4 files explicitly, then save and deploy:

```bash
git add Dockerfile fly.toml live_strategy_runner.py paper_outcome_tracker.py reporting/all_engine_performance.py strategies/manifest.py strategies/registry.py strategies/generation_four.py generation_four_paper_tracker.py reporting/generation_four_performance.py research_tools/g4_review benchmarks/benchmark_generation_four.py tests/test_generation_four.py GENERATION_FOUR_RESEARCH.md GENERATION_FOUR_DEPLOY.md
git commit -m 'Add prospective G4 mechanism research and age-aware evidence review'
git push origin modular-bot
fly deploy -a schwab --remote-only
fly status -a schwab
fly ssh console -a schwab
```

The proposed Fly configuration sets `ENABLE_G4_PAPER=1`; a Fly secret with the same name may override that setting. Check the effective value below rather than assuming it. Existing G1–G3 controls remain unchanged.

## 3. Verify activation in production

At the production SSH prompt:

```bash
python - <<'PY'
import ast,json,os
from pathlib import Path
from strategies import registry,generation_four as g4
from generation_four_paper_tracker import FILE_STEM
assert os.getenv('ENABLE_G4_PAPER')=='1'
assert not registry.FAILED_STRATEGIES
assert sum(s.name in g4.ALL_IDS for s in registry.MINUTE_STRATEGIES)==36
fn=next(n for n in ast.parse(Path('/app/live_strategy_runner.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='live_order_placement_enabled')
assert len(fn.body)==2 and isinstance(fn.body[-1],ast.Return) and isinstance(fn.body[-1].value,ast.Constant) and fn.body[-1].value.value is False
root=Path('/data')
manifest=json.loads((root/(FILE_STEM+'_manifest.json')).read_text())
assert manifest['population_hash']==g4.POPULATION_HASH
assert manifest['rule_source_sha256']==g4.RULE_SOURCE_SHA256
births=json.loads((root/(FILE_STEM+'_births.json')).read_text())
assert set(births)==set(g4.ALL_IDS)
status=json.loads((root/(FILE_STEM+'_status.json')).read_text())
assert status['broker_execution_enabled'] is False
assert status['population']==36
assert status['quote_freshness_enforced'] and status['displayed_liquidity_enforced']
print('G4 PAPER ACTIVATION VERIFIED')
print('birth range:',min(births.values()),max(births.values()))
print('manifest:',manifest)
print('status:',status)
PY
ps -eo pid,pcpu,pmem,rss,etime,args --sort=-pcpu | head -20
free -h
df -h /data
tail -80 /data/bot_output.txt
```

Births/manifest/status require the strategy runner to have initialized. If they are absent immediately after deploy, inspect supervisor/import logs and effective flags. A registry import alone does not establish activation. After-hours activation will legitimately have no trades; coverage needs the next regular session and contiguous warmup. Do not make fake production fills to prove the tracker works.

The all-engine report should show 36 G4 BA rows after births exist, including `no_entries` rows when appropriate. Observation coverage records establish when a zero return is an observed eligible experiment rather than missing data.

After a full session, use the next New York calendar date as `--as-of` so the just-finished date is complete:

```bash
python -m research_tools.g4_review.report --root /data --as-of 2026-10-09
```

Change the date appropriately. Reports do not alter controls or retire modules.

## Disable new G4 admissions while draining

From the Mac terminal after exiting SSH:

```bash
fly secrets set ENABLE_G4_PAPER=0 -a schwab
fly ssh console -a schwab
```

The runner still reconstructs the G4 tracker when its births file exists and continues observing exits. Keep all G4 source and persistent files until residual positions drain; deleting the tracker or rolling back to an image without it can strand simulated positions. Remove an overriding disabled secret or set it to one for a deliberate future reactivation, without resetting births. Do not change old rule identities or source hashes in place.
