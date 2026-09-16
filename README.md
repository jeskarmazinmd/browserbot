# Isolated Schwab executor v2

The executor loads exactly one hash-pinned strategy plugin. Strategy code emits
`TradeIntent` values but cannot access broker credentials. The permanent
executor validates quantity, symbol, price, freshness, market hours, positions,
and active orders before submission.

`MANUAL_TEST1` is a one-shot connectivity plugin, not a trading strategy. Live
mode is impossible unless its exact SHA-256 and at least one symbol are
allowlisted.

## Local verification

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile *.py plugins/manual_test1/strategy.py
sha256sum plugins/manual_test1/strategy.py
```

Expected plugin hash for this version:

```text
9bc2a9fab87c17a9ea46f08af9ab03125070cbaba31f2eac41f2a3d41ab4aed6
```

## Deployment sequence

Deploy with live mode false. Configure the existing trading app key, secret,
and its exact registered callback URL as Fly secrets. Never copy the research
token file. Create a new token using `python executor_auth.py` inside an SSH
console, then verify with `python executor_status.py`.

Only after account, positions, and orders are correct should live mode, the
symbol allowlist, maximum notional, and plugin hash be configured. Arming is:

```bash
python executor_control.py --symbol SYMBOL --side BUY --limit PRICE \
  --confirm 'ARM ONE SHARE BUY SYMBOL AT PRICE'
```

The intent expires after 45 seconds and is consumed once. A later SELL requires
a separate explicit arm and the executor verifies that at least one long share
exists. Cancel an unfilled order with:

```bash
python executor_status.py --cancel-order-id ID --confirm 'CANCEL ORDER ID'
```
