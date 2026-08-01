"""Self-contained metadata and rules for strategy R."""
STRATEGY_ID = 'R'
DESCRIPTION = 'Morning-only filter'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'end_minute_et': 660}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
