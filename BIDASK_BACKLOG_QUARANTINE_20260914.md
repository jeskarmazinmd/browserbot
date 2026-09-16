# Bid/ask historical backlog quarantine — 2026-09-14

Follow-up to the immediate mirroring repair.

- On restart, pending V3 entry or exit prices older than 60 seconds are moved
  to the audit-only quarantine ledger rather than repriced using a later quote.
- A stale pending exit also retires its corresponding active B/A twin without
  inventing P&L.
- Fresh pending records survive an ordinary quick restart.
- Status reports quarantined entry/exit counts and the quarantine path.
- `live_promotion_ready` now follows current prospective parity.

Focused result: 19 tests passed, plus production-module syntax compilation.
No deployment command was run while building this patch.
