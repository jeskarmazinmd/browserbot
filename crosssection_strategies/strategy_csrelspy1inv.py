from .inverted import InvertedStrategy
from .strategy_csrelspy1 import Strategy as Original
STRATEGY_ID="CSRELSPY1INV";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
class Strategy(InvertedStrategy):
 def __init__(self):super().__init__(Original,STRATEGY_ID)
