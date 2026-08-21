"""Self-contained metadata and rules for strategy C2."""
STRATEGY_ID = 'C2'
DESCRIPTION = 'Strategy B entry with no-new-high timeout exit'
FAMILY = 'C'
PAPER_ONLY = True
CONFIG = {'activation_gain_pct': 0.3, 'no_new_high_seconds': 30.0, 'stop_loss_fraction': 0.02}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
