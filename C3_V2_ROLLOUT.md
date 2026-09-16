# C3 shadow-v2 rollout

This package upgrades execution measurement without enabling broker orders.
It preserves the C3N25S10 thesis: 0.25% rebound, 1% stop, +0.3% activation,
and a 30-second no-new-high exit.

## Included

- `c3_live_logic.py`: deterministic executable-side state machine.
- `c3_live_runtime.py`: atomic state, durable dedupe, sequenced event outbox.
- `c3_live_service_v2.py`: Schwab/Fly adapter and restartable bar cache.
- `Dockerfile.c3live.v2`: shadow-v2 entry point.
- `tests/test_c3_live_logic.py` and `tests/test_c3_live_runtime.py`.

## Safety changes

- Entry decisions and fills use the ask; activation, highs, stops, and exits use
  the bid.
- Quote timestamps are captured after network receipt. Source times validate
  freshness; local monotonic observation order drives strategy timers.
- Bad entry liquidity delays an entry rather than deleting the setup.
- Wide spreads block entries but do not hide adverse executable exit bids.
- A pending dynamic-exit deadline is immutable; a stop outranks it.
- State, open positions, cash, signal dedupe, and audit sequence survive restart.
- Corrupt recovery state fails closed instead of silently starting empty.
- The Docker entry point still refuses `LIVE_ORDER_PLACEMENT_ENABLED != 0`.

## Local verification

Copy the four Python files and two test files into the repository, then run:

```bash
python3 -m unittest -v tests/test_c3_live_logic.py tests/test_c3_live_runtime.py
python3 -m py_compile c3_live_logic.py c3_live_runtime.py c3_live_service_v2.py
```

Do not overwrite the current shadow ledger. V2 intentionally writes:

- `/data/c3_live_state_v2.json`
- `/data/c3_live_shadow_v2.jsonl`
- `/data/c3_live_operations_v2.jsonl`
- `/data/c3_live_bars_v2.json`

## Deploy as shadow only

Keep `LIVE_ORDER_PLACEMENT_ENABLED = "0"`. Change the C3 Dockerfile setting in
`fly.c3live.toml` to `Dockerfile.c3live.v2`, then:

```bash
fly deploy --config fly.c3live.toml --ha=false
fly status -a schwab-c3-live
fly ssh console -a schwab-c3-live -C 'cat /data/c3_live_status.json'
fly logs -a schwab-c3-live
```

Expected status mode is `SHADOW_V2`. If state or the bar checkpoint is corrupt,
the machine should halt; inspect and repair it rather than deleting it blindly.

## Go-live gates not yet satisfied

The runtime deliberately has no broker adapter. Before real orders, add and test
broker order IDs, acknowledgements, partial fills, cancel/replace, reconciliation,
broker-held protective stops, buying-power reconciliation, kill switches, and
startup reconciliation against actual Schwab positions and open orders.

Run V2 through full market sessions and compare its sequenced bid/ask results
against the old paper and hybrid models. Tune execution parameters only on
separate candidate configurations; do not mutate the baseline C3 thesis in place.
