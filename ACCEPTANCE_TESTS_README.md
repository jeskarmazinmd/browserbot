# BrowserBot Monday acceptance suite

Run locally from the project virtual environment:

```bash
source .venv/bin/activate
python run_acceptance.py
```

The suite verifies:

- exactly 60 uniquely discoverable strategy modules;
- the intended split of 4 flash strategies, 25 independent scanners, and 31 derived/reporting variants;
- metadata/configuration for every derived variant;
- positive signal, near-threshold rejection, entry validation, and stop calculations for A/B/D/H;
- one deterministic positive signal fixture for every independent scanner;
- clear-negative handling for every independent scanner;
- registry exception isolation;
- replay history and event logging.

A passing suite is necessary but not sufficient for deployment. Full-day replay regression and live smoke checks remain separate gates.
