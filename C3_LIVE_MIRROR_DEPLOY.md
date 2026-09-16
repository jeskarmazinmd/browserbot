# C3N25S10 autonomous mirror-shadow revision

This bundle changes only `schwab-c3-live`. It does not modify or depend on the
research process for trading decisions or market data; the existing token lease
remains the current authentication mechanism.

## Behavioral changes

- A confirmed rebound fills immediately at the contemporaneous executable ask.
- The artificial 250 ms shadow-order phase is bypassed. Real broker latency can
  be measured only after an actual broker adapter is enabled later.
- C2 exits fill on the first qualifying executable bid observation rather than
  creating another artificial delayed shadow order.
- Setup IDs use `C3N25S10|SYMBOL|minute`, matching the research ledger format.
- Quote freshness is 15 seconds and maximum entry spread is 1.00%. These remain
  real executability gates while avoiding the previous 2.5-second/0.25% rules
  that rejected nearly every candidate.
- The Fly VM matches the research app's eight shared CPUs and uses 2 GB RAM so
  full-universe snapshot parsing is not constrained to one CPU.
- Real order placement remains hard-disabled.

## Install locally

From the repository root, unpack the returned archive over the named files only:

```bash
tar -xzf c3_live_mirror_patch.tgz
python3 test_c3_live_mirror.py
python3 -m py_compile c3_live_logic.py c3_live_runtime.py c3_live_service_v2.py
git diff -- c3_live_logic.py c3_live_service_v2.py fly.c3live.toml
```

## Deploy safely

The existing Fly volume is not overwritten by deployment. Preserve the old
shadow state and start the comparison with a clean portfolio:

```bash
fly ssh console -a schwab-c3-live -C 'sh -lc "stamp=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p /data/archive-$stamp; for f in /data/c3_live_state_v2.json /data/c3_live_status.json /data/c3_live_shadow_v2.jsonl; do [ ! -e $f ] || cp -p $f /data/archive-$stamp/; done; mv /data/c3_live_state_v2.json /data/c3_live_state_v2.pre-mirror.json 2>/dev/null || true"'
fly deploy -c fly.c3live.toml
```

Do this after market close or before the next session because resetting the
shadow state intentionally drops any old simulated pending entries/positions.
The previous state and ledger remain recoverable on the volume.

## Verify

```bash
fly status -a schwab-c3-live
fly logs -a schwab-c3-live
fly ssh console -a schwab-c3-live -C 'cat /data/c3_live_status.json'
```

Expected status:

- `strategy_id` is `C3N25S10`.
- `mode` is `SHADOW_V2`.
- `live_order_placement_enabled` is `false`.
- `universe_fetch_seconds` should improve materially from the prior ~89 seconds.
- New ledger setup IDs begin with `C3N25S10|`.

Run for at least one complete market session before judging overlap. Compare
research and live by setup minute/symbol, allowing separately sampled boundary
cases, and separately report signal overlap, entry-price slippage, exit-reason
agreement, and P/L difference.
