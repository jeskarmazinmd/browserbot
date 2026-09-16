# Minute strategy shard containment fix

Root cause: `MinuteStrategyPool.evaluate()` raised `SystemExit` for worker death,
timeout, IPC failure, and sequence mismatch. `SystemExit` bypassed the runner's
`except Exception` guard, causing the critical strategy worker to exit and the
supervisor to restart the complete machine.

This patch:

- removes all pool `SystemExit` paths;
- waits for shard responses without head-of-line blocking;
- preserves and returns results from healthy shards;
- terminates and recreates only a failed shard;
- attributes a `MinuteStrategyShardError` to every strategy in that shard;
- logs `MINUTE_STRATEGY_SHARD_RESTART` with shard, reason, strategy IDs, and
  restart count;
- leaves the parent pool and production machine running.

A restarted shard begins with fresh bounded strategy state. Strategies therefore
warm naturally from subsequent completed-minute snapshots; they do not emit
until their own history requirements are met. Healthy shards retain their state.

## Verification

```bash
python3 -m unittest discover \
  -s tests \
  -p 'test_minute_strategy_pool.py' \
  -v

python3 -m py_compile \
  strategies/registry.py \
  tests/test_minute_strategy_pool.py

git diff --check
```

The suite includes injected dead-worker, timeout, and broken-pipe failures.

## Production verification

After deployment, confirm the machine no longer restarts and inspect any shard
recovery events:

```bash
fly logs -a schwab --no-tail |
grep -E 'MINUTE_STRATEGY_SHARD_RESTART|MINUTE_STRATEGY_EVALUATION_ERROR|MINUTE_STRATEGY_BATCH' |
tail -80

fly machine status 7813422f149398 -a schwab
```
