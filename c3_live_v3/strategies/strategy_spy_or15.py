"""Paper-only SPY fifteen-minute opening-range breakout."""
from .spy_family import OpeningRangeSPYStrategy
STRATEGY_ID = "SPY_OR15"
PAPER_ONLY = True
class SPYOR15Strategy(OpeningRangeSPYStrategy):
    name = STRATEGY_ID
    range_minutes = 15
