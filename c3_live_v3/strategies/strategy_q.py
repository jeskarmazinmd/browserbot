"""Self-contained metadata and rules for strategy Q."""
STRATEGY_ID = 'Q'
DESCRIPTION = 'Volatility-normalized drop filter'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'min_volatility_units': 3.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
