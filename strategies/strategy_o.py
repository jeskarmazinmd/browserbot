"""Self-contained metadata and rules for strategy O."""
STRATEGY_ID = 'O'
DESCRIPTION = 'Second-leg rebound setup'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'pullback_from_first_high_pct': 0.1, 'rebound_from_pullback_low_pct': 0.1, 'stop_loss_fraction': 0.02}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
