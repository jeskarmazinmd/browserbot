# $5,000 intraday hypothetical-close report

This adds a read-only terminal report comparing every parent/LAST module with
its realistically priced bid/ask twin. It combines today's completed trades
with today's still-open trades, marks parent positions at the latest LAST and
long bid/ask positions at the latest BID, and runs both sides through the
existing capital-constrained simulation (1% risk per trade, 20% maximum
position, whole shares).

The detailed table includes full LAST, paired LAST, paired B/A, realized B/A,
execution drag, open pairs, and coverage. Missing B/A twins are disclosed and
never synthesized. Open bid marks older than three minutes are rejected.

The existing performance worker automatically persists immutable completed-day
paired summaries. The normal command displays recent days as columns, so no
terminal output needs to be manually saved. It never closes positions.

## Verify before deployment

```bash
./.venv/bin/python -m pytest -q \
  tests/test_capital_intraday_report.py \
  tests/test_capital_performance.py \
  tests/test_capital_performance_worker.py \
  tests/test_bidask_repricing_tracker.py
```

## Run after deployment

```bash
fly ssh console -a schwab -C "python -m reporting.capital_intraday_report"
```

Useful views:

```bash
python -m reporting.capital_intraday_report --days 10 --sort overall
python -m reporting.capital_intraday_report --days all --sort drag
python -m reporting.capital_intraday_report --sort today
python -m reporting.capital_intraday_report --module C3MG_P10
python -m reporting.capital_intraday_report --detail
```

An optional historical market-day argument is supported, though the open-trade
mark is primarily intended for the current day:

```bash
python -m reporting.capital_intraday_report --day 2026-09-15
```
