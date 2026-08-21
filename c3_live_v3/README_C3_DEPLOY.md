# C3 parity clone

Safety defaults: C3_ONLY=1 and LIVE_ORDER_PLACEMENT_ENABLED=0.
The clone borrows the current market access token from schwab's private token-lease endpoint and never refreshes/writes the market token.

Important: the runner's C3N25S10 strategy, flash detector, pending rebound path, quote-source minute collapse, and PaperOutcomeTracker are copied from the research snapshot. The runner still evaluates A/B/D/H compatibility flash controls because the legacy orchestration has hard-coded reporting assumptions around those IDs; unrelated minute-strategy subprocesses are disabled. Only C3 parity should be judged for promotion.

Required Fly secret on schwab-c3-live: TOKEN_LEASE_SECRET must match schwab.
Required universe: /data/research_universe_YYYYMMDD.csv (or eligible_symbols equivalent). Copy the same daily universe used by schwab before starting the clone.

Do not enable live orders until same-session setup_id and PAPER_EXIT parity has been measured.
