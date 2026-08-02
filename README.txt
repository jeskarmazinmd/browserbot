GENERIC STRATEGY PACK — PHASE 1

Adds five paper-only generic strategies:
  GT1 generic trend continuation
  GP1 generic pullback in an uptrend
  GR1 generic repeated-support rejection
  GE1 generic selling exhaustion
  GM1 generic mean reversion

No universe filter or market-regime gate is applied in this phase.
All signals use the runner's existing independent strategy pipeline,
30-minute symbol cooldown, separate strategy IDs, and live_order_placement=False.

INSTALL
1. Copy detectors/ into your project root.
2. Copy the six files in strategies/ into your existing strategies/ folder.
3. Replace live_strategy_runner.py with the included version.
4. leaderboard_writer.py is included unchanged; its reporting engine should
   discover strategy event files by strategy ID as it does for other independent strategies.
5. Run: python -m py_compile live_strategy_runner.py detectors/*.py strategies/*.py
6. Deploy normally.

The included runner differs from the uploaded runner only by importing
strategies.generic_registry and adding its outputs to the existing independent
strategy evaluation results.
