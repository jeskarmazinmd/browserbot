"""Paper-only SPY cross-asset risk-on confirmation."""
from .spy_family import SPYCrossAssetStrategy
STRATEGY_ID = "SPY_XA1"
PAPER_ONLY = True
class SPYXA1Strategy(SPYCrossAssetStrategy):
    name = STRATEGY_ID
