"""Self-contained metadata and rules for strategy K4."""
STRATEGY_ID = 'K4'
DESCRIPTION = 'Strategy A post-entry exit research variant'
FAMILY = 'K'
PAPER_ONLY = True
CONFIG = {'mode': 'conditional_return', 'seconds': 30, 'min_return_pct': 0.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
