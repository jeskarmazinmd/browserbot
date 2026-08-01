"""Self-contained metadata and rules for strategy K8."""
STRATEGY_ID = 'K8'
DESCRIPTION = 'Strategy A post-entry exit research variant'
FAMILY = 'K'
PAPER_ONLY = True
CONFIG = {'mode': 'conditional_reach', 'seconds': 60, 'required_gain_pct': 0.2}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
