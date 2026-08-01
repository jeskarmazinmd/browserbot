"""Self-contained metadata and rules for strategy S."""
STRATEGY_ID = 'S'
DESCRIPTION = 'Market-confirmed filter'
FAMILY = 'LS'
PAPER_ONLY = True
CONFIG = {'max_market_5m_loss_pct': 0.15, 'min_market_1m_return_pct': 0.0}

def metadata():
    return {"strategy_id": STRATEGY_ID, "description": DESCRIPTION, "family": FAMILY, "paper_only": PAPER_ONLY, "config": dict(CONFIG)}
