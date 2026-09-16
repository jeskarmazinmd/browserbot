# Module Factory staged installation

The factory is paper/shadow-only. It contains no broker client and cannot
place orders. Deploy it disabled, verify the image, then enable five shadow
slots for the first observation session.

The separate after-hours research controller uses both internal market-data
scientists and bounded OpenAlex literature retrieval. External material is
stored as cited inspiration, capability-screened, and must pass the same
sealed validation and bid/ask shadow process.

## Safety defaults

- `FACTORY_SHADOW_ENABLED=0` unless explicitly enabled
- 100 hard maximum shadow modules; adaptive scaler starts at 5
- 1,024 MB minimum available memory
- 1,024 MB minimum free `/data` storage
- maximum one-minute load of 1.25 per logical CPU
- three consecutive healthy checks required after a resource pause
- strict `BIDASK_EXEC_V1`; no last-price fallback
- automatic disable only after 10 sessions and 100 executable outcomes
- no automatic production/live promotion
- resource-driven reversible parking (never counted as scientific failure)
- immediate capacity contraction and five-module gradual expansion
- four immutable discovery days followed by one sealed validation day
- validation datasets are permanently spent after one frozen batch
- only faithfully representable validated hypotheses become modules

## Local verification

```bash
python -m pytest -q research_tools/module_factory
```

## Staged rollout

Deploy with the factory disabled first. After verifying normal application
health, enable five slots:

```bash
fly secrets set -a schwab \
  FACTORY_SHADOW_ENABLED=1 \
  FACTORY_RESEARCH_ENABLED=1 \
  FACTORY_LITERATURE_ENABLED=0 \
  FACTORY_MAX_SHADOW_MODULES=100 \
  FACTORY_MIN_MEMORY_AVAILABLE_MB=1024 \
  FACTORY_MIN_DATA_FREE_MB=1024 \
  FACTORY_MAX_LOAD_PER_CPU=1.25 \
  FACTORY_HEALTHY_CHECKS_TO_RESUME=3 \
  FACTORY_MIN_PRUNE_SESSIONS=10 \
  FACTORY_MIN_PRUNE_EVENTS=100
```

Inspect `/data/module_factory/health.json` and supervisor logs. Increasing
the cap to 12 and later 24 should be a separate decision after observing a
complete trading session at each stage.

`FACTORY_RESEARCH_ENABLED=1` already invokes the literature scientist, so the
standalone `FACTORY_LITERATURE_ENABLED` worker should remain off. Research is
deferred during market hours and whenever the resource governor denies it.
