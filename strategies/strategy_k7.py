"""Self-contained metadata and rules for strategy K7."""
STRATEGY_ID = 'K7'
DESCRIPTION = 'Strategy A post-entry exit research variant'
FAMILY = 'K'
PAPER_ONLY = True
CONFIG = {'mode': 'conditional_mfe', 'seconds': 60, 'min_mfe_pct': 0.3}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
