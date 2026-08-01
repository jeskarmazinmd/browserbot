"""Self-contained metadata and rules for strategy K1."""
STRATEGY_ID = 'K1'
DESCRIPTION = 'Strategy A post-entry exit research variant'
FAMILY = 'K'
PAPER_ONLY = True
CONFIG = {'mode': 'fixed_exit', 'seconds': 30}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
