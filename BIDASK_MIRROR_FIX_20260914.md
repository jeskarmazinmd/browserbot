# Bid/ask mirror repair — 2026-09-14

This patch repairs the core single-leg LAST → V2/IOC → V3 bid/ask handoff.

## Guarantees

- Every signal accepted by the parent `PaperOutcomeTracker` is registered with
  both bid/ask consumers immediately through one handoff.
- Both consumers receive the same freshly requested quote snapshot.
- V3 registration is independent of V2/IOC quote validation or fill outcome.
- Quote retrieval failure leaves both mirrored signals pending; it cannot lose
  the accepted parent event.
- V3 does not run its own exit state machine. It copies the parent exit reason
  and timestamp exactly, repricing only the executable exit price.
- Performance output reports parent/V3 entry and exit coverage, including exact
  missing and orphan setup IDs and a `parity_ok` flag.

## Files

- `bidask_paper_outcome_tracker.py`
- `live_strategy_runner.py`
- `reporting/all_engine_performance.py`
- `tests/test_bidask_repricing_tracker.py`
- `tests/test_all_engine_performance.py`

## Verification

Focused command:

```sh
python3 -m unittest -v \
  tests.test_bidask_repricing_tracker \
  tests.test_all_engine_performance
```

Result: 18 tests passed. The three modified production modules also pass
`python3 -m py_compile`.

Repository-wide discovery ran 507 tests and produced the same unrelated
baseline result as the supplied archive: 14 failures and 23 errors. The clean
archive itself ran 503 tests with 14 failures and 23 errors; the four added
tests account for the count difference and all four pass.

No deployment command was run.
