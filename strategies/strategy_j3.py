"""Self-contained metadata and rules for strategy J3."""
STRATEGY_ID = 'J3'
DESCRIPTION = 'Strategy B post-entry failure-management variant'
FAMILY = 'J'
PAPER_ONLY = True
CONFIG = {'stop_loss_fraction': 0.01, 'checkpoint_seconds': 15.0, 'checkpoint_max_return_pct': 0.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
