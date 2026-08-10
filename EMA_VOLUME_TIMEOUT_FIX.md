# EMA volume-confirmation timeout fix

This patch prevents EMA1/EMA1RR's on-demand Schwab volume checks from blocking
their entire minute-strategy shard.

## Behavior

- EMA crossover symbols are confirmed as one bounded batch instead of one
  serial API call at a time.
- EMA1 and EMA1RR reuse the same results for the same market minute.
- At most 24 symbols are submitted per minute, using four request workers.
- The two EMA modules share one 18-second batch deadline.
- Each Schwab client is reused within its request thread and configured with a
  five-second request timeout when the client supports `set_timeout`.
- Missing, over-budget, failed, or late confirmations fail closed and produce
  no EMA signal. They cannot terminate the shard.
- `EMA_VOLUME_CONFIRMATION_BATCH` logs expose requested, cached, submitted,
  completed, timed-out, and budget-skipped counts.

Defaults may be changed with `EMA_VOLUME_MAX_WORKERS`,
`EMA_VOLUME_MAX_SYMBOLS_PER_MINUTE`, `EMA_VOLUME_BATCH_TIMEOUT_SECONDS`, and
`EMA_VOLUME_REQUEST_TIMEOUT_SECONDS`.

## Verify before deployment

```bash
python3 -m unittest discover -s tests -p 'test_ema_volume*.py' -v
python3 -m unittest discover -s tests -p 'test_minute_strategy_pool.py' -v
python3 -m py_compile \
  live_strategy_runner.py \
  strategies/registry.py \
  strategies/strategy_ema1.py \
  strategies/strategy_ema1rr.py \
  strategies/ema_volume_batch.py
git diff --check
```

## Production verification

After deployment, look for `EMA_VOLUME_CONFIRMATION_BATCH`. Confirm that
`MINUTE_STRATEGY_SHARD_RESTART` does not recur for the former EMA shard. A
batch with `timed_out` or `skipped_budget` above zero indicates fail-closed
degradation for EMA volume confirmation, not a stopped strategy worker.
