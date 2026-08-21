"""Paper-only SPY thirty-minute opening-range breakout."""
from .spy_family import OpeningRangeSPYStrategy
STRATEGY_ID = "SPY_OR30"
PAPER_ONLY = True
class SPYOR30Strategy(OpeningRangeSPYStrategy):
    name = STRATEGY_ID
    range_minutes = 30
    break_buffer_pct = 0.07
    target_pct = 0.60
    stop_pct = 0.35
