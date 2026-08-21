"""Paper-only SPY five-minute opening-range breakout."""
from .spy_family import OpeningRangeSPYStrategy
STRATEGY_ID = "SPY_OR5"
PAPER_ONLY = True
class SPYOR5Strategy(OpeningRangeSPYStrategy):
    name = STRATEGY_ID
    range_minutes = 5
    break_buffer_pct = 0.03
    target_pct = 0.40
    stop_pct = 0.25
