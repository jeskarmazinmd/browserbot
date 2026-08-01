"""Self-contained metadata and rules for strategy I."""
STRATEGY_ID = 'I'
DESCRIPTION = 'Strategy A with fast rebound confirmation'
FAMILY = 'overlay'
PAPER_ONLY = True
CONFIG = {'max_confirmation_delay_seconds': 30.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
