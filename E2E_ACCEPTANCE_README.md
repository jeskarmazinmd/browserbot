# BrowserBot end-to-end acceptance layer

This layer complements the existing module-level acceptance suite.

It runs the actual `live_strategy_runner.main()` loop in replay mode and verifies:

1. all 25 independent strategy IDs pass through runner orchestration and are logged as `SIGNAL` events;
2. flash strategies create pending entries, confirm rebounds, and write `SIGNAL` events;
3. threshold near misses are written to `bot_events.jsonl` and appear in replay dashboard history;
4. replay terminates cleanly.

## Important bug fixed

The end-to-end near-miss test found stale undefined Strategy H constants in the runner:

`STRATEGY_H_MIN_FLASH_DROP_PCT`, `STRATEGY_H_MAX_FLASH_DROP_PCT`,
`STRATEGY_H_MIN_PRE_R2`, and `STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR`.

`patch_h_near_miss_aliases.py` adds aliases sourced directly from Strategy H's module configuration. It does not overwrite the runner.

## Install and run

Merge this package into the browserbot project, then run:

```bash
python3 patch_h_near_miss_aliases.py
python3 -m py_compile live_strategy_runner.py
python3 run_monday_readiness.py
```
