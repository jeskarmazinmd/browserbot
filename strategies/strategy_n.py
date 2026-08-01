"""Self-contained metadata and rules for strategy N."""
STRATEGY_ID = 'N'
DESCRIPTION = 'Adaptive trailing exit'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'activation_gain_pct': 0.3, 'trail_from_high_pct': 0.2}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
