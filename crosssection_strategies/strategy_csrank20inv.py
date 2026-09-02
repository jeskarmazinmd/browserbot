from .inverted import InvertedStrategy
from .strategy_csrank20 import Strategy as Original
STRATEGY_ID="CSRANK20INV";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
class Strategy(InvertedStrategy):
 def __init__(self):super().__init__(Original,STRATEGY_ID)
