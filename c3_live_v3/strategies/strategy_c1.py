"""Self-contained metadata and rules for strategy C1."""
STRATEGY_ID = 'C1'
DESCRIPTION = 'Strategy B entry with trailing pullback exit'
FAMILY = 'C'
PAPER_ONLY = True
CONFIG = {'activation_gain_pct': 0.3, 'pullback_from_high_pct': 0.2, 'stop_loss_fraction': 0.02}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
