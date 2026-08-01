"""Self-contained metadata and rules for strategy M."""
STRATEGY_ID = 'M'
DESCRIPTION = 'Rolling VWAP distance overlay'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'min_distance_below_vwap_pct': 0.5}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
