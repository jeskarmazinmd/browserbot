"""Self-contained metadata and rules for strategy G."""
STRATEGY_ID = 'G'
DESCRIPTION = 'Strategy C4 with 1.5% protective stop'
FAMILY = 'C'
PAPER_ONLY = True
CONFIG = {'parent_strategy': 'C4', 'stop_loss_fraction': 0.015}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
