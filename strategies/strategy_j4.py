"""Self-contained metadata and rules for strategy J4."""
STRATEGY_ID = 'J4'
DESCRIPTION = 'Strategy B post-entry failure-management variant'
FAMILY = 'J'
PAPER_ONLY = True
CONFIG = {'stop_loss_fraction': 0.01, 'checkpoint_seconds': 30.0, 'checkpoint_max_return_pct': 0.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
