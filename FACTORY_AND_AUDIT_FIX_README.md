# Factory progression and bid/ask audit fix — 2026-09-15

## Factory progression

- Replaces the memory-heavy all-at-once regime stage with atomic
  feature/state/horizon/quantile evaluation.
- Writes a durable checkpoint after every atomic regime question.
- Reuses completed checkpoints after restart and releases memory before the
  next question.
- Preserves full-resolution discovery and exact scientific outputs.
- Persists `/data/module_factory/research_status.json` so discovery stage,
  deferrals, memory errors, and unexpected errors remain observable after logs
  rotate.

The existing ten completed distribution checkpoints remain reusable. New
regime checkpoints use distinct keys and do not reinterpret old data.

## Bid/ask audit

- Populates `parent_recorded_at` for every newly mirrored V3 entry instead of
  writing `null`.
- Does not change selection, pricing, sizing, or exit logic.

## Minute pipeline

No runtime change was made. Live evidence showed 0.585 seconds evaluation,
1.102 seconds total batch time, and about 10.7 seconds of actionable lag after
minute completion. The earlier delay was deployment/startup related.

## Validation

- Focused final suite: 28 passed.
- Broad relevant suite: 453 passed.
- Seven unrelated fixture-backed tests could not run because their
  `research_data` fixtures were excluded from the supplied source archive.
- Python compilation passed for every changed runtime file.

This package does not deploy or alter `/data`.
