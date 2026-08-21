"""Paper-only SPY intraday mean-reversion rebound."""
from .spy_family import SPYMeanReversionStrategy
STRATEGY_ID = "SPY_MR1"
PAPER_ONLY = True
class SPYMR1Strategy(SPYMeanReversionStrategy):
    name = STRATEGY_ID
