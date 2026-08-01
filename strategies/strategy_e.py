"""Self-contained metadata and rules for strategy E."""
STRATEGY_ID = 'E'
DESCRIPTION = 'Strategy A with minimum flash dollar volume'
FAMILY = 'overlay'
PAPER_ONLY = True
CONFIG = {'min_flash_dollar_volume_3m': 1200000}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
