"""Paper-only SPY breadth-confirmed momentum."""
from .spy_family import SPYBreadthStrategy
STRATEGY_ID = "SPY_BR1"
PAPER_ONLY = True
class SPYBR1Strategy(SPYBreadthStrategy):
    name = STRATEGY_ID
