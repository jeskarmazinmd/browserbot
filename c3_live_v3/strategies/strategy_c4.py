"""Self-contained metadata and rules for strategy C4."""
STRATEGY_ID = 'C4'
DESCRIPTION = 'Strategy B entry with negative-slope exit'
FAMILY = 'C'
PAPER_ONLY = True
CONFIG = {'activation_gain_pct': 0.3, 'slope_window_seconds': 30.0, 'negative_slope_pct_per_minute': -0.2, 'stop_loss_fraction': 0.02}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
