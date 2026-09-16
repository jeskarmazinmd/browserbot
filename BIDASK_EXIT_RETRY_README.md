# V3 exit quote retry

V3 now obtains a fresh bid for paper exit repricing from the same Schwab
response as the live execution quote. An unchanged or absent ask does not
prevent V3 from repricing a SELL. Live IOC decisions continue to require a
valid, fresh two-sided quote.

A parent exit may resolve for at most 120 seconds from its recorded exit
timestamp; the resolved V3 row records the bid timestamp and delay. Unpriced
exits are quarantined after that window, including during normal operation.
Recovery after a restart applies the same bound. Yesterday's unresolved exits
cannot be assigned today's bid; the quarantine file is the audit trail.

The runner emits `BIDASK_REPRICE_EXIT_RETRY` diagnostics at most once per
minute when exits are pending, showing pending exits/symbols and available bid
counts. This is a paired repricing benchmark, not an autonomous bid-based
strategy.

## Verify on the Mac

```bash
./.venv/bin/python -m pytest -q tests/test_bidask_repricing_tracker.py
```

## Verify after deployment

```bash
cat /data/paper_signal_v3_bidask_repricing_status.json
```

Watch whether pending exits resolve within the grace window during an open
session and whether unresolved exits appear in the quarantine audit. The 667
exits pending after the September 15 close are too old to price accurately from
a September 16 quote; expect them to be quarantined after the worker restarts.
