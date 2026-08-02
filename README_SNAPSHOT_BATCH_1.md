# Snapshot Strategy Migration — Batch 1

Migrated: EMA1, EMA2, EMA3, SMA1, VWEMA1.

Key design:
- consumes one `MarketSnapshot` per Schwab cycle;
- no pandas, tape, candles, or runner context;
- windows are continuous-time over raw snapshots;
- old `strategies.registry` is untouched;
- `snapshot_registry.py` allows side-by-side validation.

EMA1 requires `Quote.total_volume`; it computes instantaneous cumulative-volume rate and compares it with its rolling raw-snapshot baseline.
