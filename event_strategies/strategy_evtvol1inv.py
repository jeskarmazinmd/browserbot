from .inverted import InvertedStrategy
from .strategy_evtvol1 import Strategy as Original
PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
class Strategy(InvertedStrategy):
 def __init__(self):super().__init__(Original,"EVTVOL1INV")
