"""Paper-only SPY multi-factor ensemble."""
from .spy_family import SPYEnsembleStrategy
STRATEGY_ID = "SPY_ENS1"
PAPER_ONLY = True
class SPYENS1Strategy(SPYEnsembleStrategy):
    name = STRATEGY_ID
