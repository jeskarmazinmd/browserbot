from .inverted import InvertedStrategy
from .strategy_csbreadth1 import Strategy as Original
STRATEGY_ID="CSBREADTH1INV";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
class Strategy(InvertedStrategy):
 def __init__(self):super().__init__(Original,STRATEGY_ID)
