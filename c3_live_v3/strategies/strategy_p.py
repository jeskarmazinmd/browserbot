"""Self-contained metadata and rules for strategy P."""
STRATEGY_ID = 'P'
DESCRIPTION = 'Strong pre-trend filter'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'min_pre_return_pct': 0.75, 'min_pre_r2': 0.5}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
