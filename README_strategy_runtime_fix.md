# Full-universe strategy runtime fix

This patch keeps every currently registered minute strategy and all 2,677
symbols. It changes execution mechanics only:

- stateful minute strategies are assigned once to persistent process shards;
- every shard receives each completed minute and returns its signals to the
  parent in the original strategy order;
- worker death or a 55-second timeout terminates the runner so the supervisor
  can restart it cleanly rather than leaving a falsely healthy process;
- the A/B flash path builds one gap-preserving RTH minute matrix per cycle
  instead of resampling the same cache separately 2,677 times;
- per-snapshot runtime and lag are logged as `MINUTE_STRATEGY_SNAPSHOT` and
  `MINUTE_STRATEGY_BATCH`.

## Production-cache measurements

- Serial 85-module replay: 320.5 seconds for 49 snapshots.
- Eight-shard replay: 78.5 seconds for the same 49 snapshots.
- Signals: 44,253 in both modes; zero evaluation errors.
- Latest serial minute: approximately 9.8 CPU-seconds.
- Flash scan: 22.1 seconds before, 3.1 seconds after.
- Gap-preserving flash series matched the prior implementation in sampled
  equivalence checks.

## Apply and test

From the repository root:

```bash
tar -xzf strategy_runtime_full_universe_fix.tgz -C .
python3 -m unittest discover -s tests -p 'test_minute_strategy_pool.py' -v
python3 -m py_compile live_strategy_runner.py strategies/registry.py
git diff --check
git diff -- live_strategy_runner.py strategies/registry.py tests/test_minute_strategy_pool.py
```

The default shard count is `min(8, os.cpu_count())`. It can be overridden with
`MINUTE_STRATEGY_SHARDS`. The default per-minute worker deadline is 55 seconds
and can be overridden with `MINUTE_STRATEGY_TIMEOUT_SECONDS`.

## Deploy and verify

```bash
git add live_strategy_runner.py strategies/registry.py tests/test_minute_strategy_pool.py
git commit -m "Parallelize full-universe strategy evaluation"
fly deploy -a schwab
```

After deployment:

```bash
fly logs -a schwab --no-tail | grep -E \
'MINUTE_STRATEGY_POOL_ONLINE|MINUTE_STRATEGY_WARMUP|MINUTE_STRATEGY_BATCH|MINUTE_STRATEGY_SNAPSHOT|SCAN_SUMMARY' | tail -80
```

Expected startup line on the current eight-CPU machine:

```text
MINUTE_STRATEGY_POOL_ONLINE shards=8 strategies=85
```

The first batch is warm-up and intentionally does not record historical
signals. Subsequent snapshots should have low `lag_seconds`, and `SCAN_SUMMARY`
should resume after the warm-up batch.
