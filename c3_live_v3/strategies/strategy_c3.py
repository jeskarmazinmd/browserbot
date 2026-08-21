"""Self-contained metadata and rules for strategy C3."""
STRATEGY_ID = 'C3'
DESCRIPTION = 'Strategy B entry with lower-sample decline exit'
FAMILY = 'C'
PAPER_ONLY = True
CONFIG = {'activation_gain_pct': 0.3, 'lower_samples': 3, 'min_total_decline_pct': 0.1, 'stop_loss_fraction': 0.02}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
