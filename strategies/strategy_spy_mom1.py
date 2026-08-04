"""Paper-only SPY aligned five/fifteen-minute momentum."""
from .spy_family import SPYMomentumStrategy
STRATEGY_ID = "SPY_MOM1"
PAPER_ONLY = True
class SPYMOM1Strategy(SPYMomentumStrategy):
    name = STRATEGY_ID
