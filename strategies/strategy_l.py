"""Self-contained metadata and rules for strategy L."""
STRATEGY_ID = 'L'
DESCRIPTION = 'Exhaustion volume-ratio overlay'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'min_flash_volume_ratio': 1.0, 'max_rebound_to_flash_ratio': 0.75}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
