# Full manual review generator

Run locally from the project root:

```bash
source .venv/bin/activate
python3 generate_full_manual_review.py
```

It creates `manual_review/` with one folder per strategy ID. Every folder contains a real signal record generated from the strategy module or a derived handoff record generated from its real parent metadata. A `near_miss.json` is written only when the production bot currently has a real near-miss definition. Missing near-miss paths are marked explicitly; they are not fabricated.

The command exits with status 2 until all 60 strategies have genuine production near-miss contracts. Inspect `manual_review/coverage_report.txt` and `manual_review/all_events.txt`.
