# Schwab bot reliability fix

## What changed

- Keeps the Fly Machine at 2 GB RAM.
- Replaces full-file tape trimming with streamed, atomic trimming.
- Parses the strategy tape from a temporary file instead of duplicating it in a large string.
- Reads leaderboard outcome tapes in chunks and retains only tracked symbols.
- Limits near-expiry token refresh attempts to once per minute.
- Reports quote collection from today's tape freshness, not token health alone.
- Runs all three workers under `supervisor.py`; if one exits, the others stop and Fly receives a failure exit.
- Records worker exits in `/data/worker_supervisor.jsonl`.
- Excludes local credential and archive files from Docker and Git contexts.

No signal thresholds, order sizing, entry/exit logic, or strategy mathematics were changed.

## Deploy

Back up the current local files, copy the contents of this archive into the `browserbot` folder, then run:

```bash
python3 -m py_compile live_quote_collector.py live_strategy_runner.py leaderboard_writer.py supervisor.py
fly deploy
```

Verify:

```bash
fly status -a schwab
fly logs -a schwab
```

Expected logs include `SUPERVISOR ... started`, collector cycles, and strategy diagnostics.

## Rollback

Restore the backed-up local files and run `fly deploy` again.
