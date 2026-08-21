"""Self-contained metadata and rules for strategy F."""
STRATEGY_ID = 'F'
DESCRIPTION = 'Strategy D with minimum relative flash volume'
FAMILY = 'overlay'
PAPER_ONLY = True
CONFIG = {'min_flash_volume_ratio': 0.75}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
