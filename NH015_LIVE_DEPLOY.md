# C3N25S10NH015 live deployment

This change wires only `C3N25S10NH015` to real Schwab execution inside the
main `schwab` app. `C3N25S10NH015DUP` remains paper-only and unchanged.

## Allocation parity

The live allocation ledger mirrors `reporting.capital_performance.simulate_day`:

- $5,000 virtual cash at the beginning of each New York market day
- 1% of current virtual equity risk per trade
- 20% maximum position size
- whole shares
- open positions reserve their entry cost
- released capital can be reused after a reconciled live exit
- no leverage

The live ledger uses actual realized broker P/L after exit. That means later
live quantities can legitimately diverge from paper after real slippage or an
unfilled order; those are execution effects to measure, not hide.

## Exit parity

Entry signals are the existing NH015 duration arm cloned from C3N25S10. A
broker-hosted target/stop bracket protects every filled position. After a
0.30% gain activates the C2 exit, a new high resets the clock; 15 seconds
without a new high triggers cancellation of the protective bracket followed
by a market sell. The existing 15:55 ET flatten remains the final fallback.

## Fail-closed controls

Real submission is armed only when both are true:

```text
LIVE_ORDER_PLACEMENT_ENABLED=1
LIVE_STRATEGY_ID=C3N25S10NH015
```

The trading token must resolve exactly one linked Schwab account. Before every
entry, the runner blocks on untracked broker positions, untracked active
orders, an existing position in the same symbol, failed broker reconciliation,
missing broker cash data, or insufficient non-borrowed broker cash. Margin
buying-power fields are deliberately excluded from the cash test.

`LIVE_UNFUNDED_ORDER_PROBE_ENABLED=1` is permitted only while the authorized
trading account is deliberately empty. It converts only
`insufficient_broker_cash` into an advisory so the request can reach Schwab's
order endpoint for transport testing. Remove the secret or set it to `0`
before authorizing or funding a trading account. The default is funded mode,
where insufficient cash blocks the order.

The durable files are:

```text
/data/nh015_live_allocation.json
/data/nh015_live_status.json
/data/nh015_live_audit.jsonl
/data/nh015_live_daily_history.json
```

## Apply and test locally

```bash
cd ~/Desktop/browserbot
git apply --check ~/Downloads/nh015-live-execution.patch
git apply ~/Downloads/nh015-live-execution.patch
python3 -m unittest -v \
  tests.test_live_nh015_execution \
  tests.test_c3_exit_duration_sweep
python3 -m py_compile \
  live_strategy_runner.py \
  live_nh015_execution.py \
  schwab_clients.py
```

## Deploy disarmed

Set the strategy identity while leaving the master switch off:

```bash
fly secrets set -a schwab \
  LIVE_ORDER_PLACEMENT_ENABLED=0 \
  LIVE_STRATEGY_ID=C3N25S10NH015
```

Deploy normally:

```bash
fly deploy -a schwab
```

Confirm the new runner is healthy and disarmed:

```bash
fly logs -a schwab --no-tail | tail -n 200
fly ssh console -a schwab -C 'cat /data/nh015_live_status.json'
```

The startup line must report `NH015_LIVE_BOOK_ONLINE armed=False`, with
`equity=5000.00` and no active live allocations. Do not arm if
`/data/positions.json` contains an unexplained position or if the trading
account cannot be resolved exactly.

## Arm after the disarmed verification

```bash
fly secrets set -a schwab LIVE_ORDER_PLACEMENT_ENABLED=1
```

That restarts the Fly machine. Confirm the next startup line reports
`NH015_LIVE_BOOK_ONLINE armed=True` and that account resolution succeeds.

## Compare with the benchmark

NH015 and NH015DUP continue to appear in the ordinary daily history. Live
actual return is recorded separately:

```bash
fly ssh console -a schwab -C 'cat /data/nh015_live_status.json'
fly ssh console -a schwab -C 'cat /data/nh015_live_daily_history.json'
fly ssh console -a schwab -C 'tail -n 100 /data/nh015_live_audit.jsonl'
```

Compare each day on signals attempted, broker submissions, fills, exit reason,
actual P/L and return. A same-symbol overlap may be accepted by the paper
simulator but is intentionally blocked live because Schwab reports one net
position per symbol; that skip is explicitly audited.

## Emergency stop

```bash
fly secrets set -a schwab LIVE_ORDER_PLACEMENT_ENABLED=0
```

Disarming prevents new entries. Broker-hosted target/stop exits and the
runner's existing reconciliation remain responsible for positions already
open; inspect the Schwab account directly after any emergency stop.
