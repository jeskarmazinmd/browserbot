# Bid/ask immediate mirroring fix — 2026-09-15

This patch is based on the two source files copied directly from the running
Fly.io production image on 2026-09-15. It preserves the deployed paired
coverage and stale-recovery quarantine logic.

## Changes

- Cache executable quotes for one runner cycle and fetch each newly signalled
  symbol at most once, even when many strategy variants emit together.
- Reuse the same quote snapshot for all same-symbol LAST/V2/V3 twins.
- Treat a missing quote as an attempted lookup for the rest of that cycle,
  avoiding repeated API calls and serial runner stalls.
- Evaluate executable quote freshness at processing time rather than against
  an older strategy signal timestamp.
- Preserve parent signal/entry timestamps and add parent/mirror/quote audit
  timestamps to V3 entry rows.

## Verified

- `python -m py_compile` passed for both changed runtime files.
- Focused pytest suite: 25 passed.
- Added regression coverage for per-cycle quote deduplication and delayed
  signal processing with a fresh executable quote.

## Apply locally (does not deploy)

From the browserbot repository root, extract this ZIP to a temporary directory,
then copy the files listed in `BIDASK_MIRROR_FIX_MANIFEST.txt` into matching
repository paths. Run the focused tests before deployment.

Suggested verification:

```bash
python -m pytest -q \
  tests/test_bidask_repricing_tracker.py \
  tests/test_bidask_paper_outcome_tracker.py \
  tests/test_nh015_bidask_engine_integration.py \
  tests/test_all_engine_performance.py
```

This package does not deploy or alter `/data` state.
