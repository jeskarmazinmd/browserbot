# Bounded quote requests for live and paired B/A

The shared Schwab request was sending roughly 1,350 symbols and returning HTTP 400 every cycle. The runner now requests up to 400 symbols per cycle in batches of at most 100, prioritizes active live positions and V3 pending entries/exits, and rotates through remaining active symbols. If one batch fails, successfully fetched batches remain available. The existing live IOC two-sided quote filter and V3 bid-only exit filter remain separate. No broker configuration or order placement flags change.

Apply both files from the manifest in the Mac repo. Run:

    ./.venv/bin/python -m pytest -q tests/test_bidask_repricing_tracker.py
    ./.venv/bin/python -m py_compile live_strategy_runner.py

Deploy from the committed runner overlaying the current running Fly image, rather than building from an unrelated dirty working tree. Verify NH015_EXECUTION_QUOTE_ERROR 400 stops recurring, usable_bids becomes nonzero on active pending symbols, and seen_exits begins increasing.
