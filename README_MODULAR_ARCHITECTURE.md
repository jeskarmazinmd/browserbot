# Modular strategy architecture

## Core files

- `live_quote_collector.py`: quote collection and tape maintenance only.
- `live_strategy_runner.py`: shared tape, broker, lifecycle, and orchestration only.
- `leaderboard_writer.py`: a thin process entry point only.
- `bot_output.py`: generic event persistence only.

## Strategy plug-ins

Every strategy or paper variant has one `strategies/strategy_*.py` module. Each
module owns its ID, description, family, paper/live status, and thresholds in
`CONFIG`. Scanner strategies also expose `evaluate(context)`.

`strategies/manifest.py` discovers modules automatically. Adding a strategy no
longer requires editing a core file. Set `ENABLED = False` in a scanner module,
or remove its file, to stop loading it.

## Shared engines

`reporting/engine.py` is generic reporting and paper-outcome infrastructure. It
may execute shared family algorithms, but strategy-specific values come from
strategy modules. It is not a live runner or collector core file.

## Required checks

```bash
python3 -m py_compile live_strategy_runner.py leaderboard_writer.py \
  live_quote_collector.py bot_output.py reporting/*.py strategies/*.py
python3 audit_core_modularity.py
```

This package still requires replay/equivalence testing before deployment.
