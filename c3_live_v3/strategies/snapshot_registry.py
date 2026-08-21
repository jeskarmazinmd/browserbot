"""Registry for snapshot-native strategies during parallel migration."""
from .strategy_ema1 import EMA1Strategy
from .strategy_ema2 import EMA2Strategy
from .strategy_ema3 import EMA3Strategy
from .strategy_sma1 import SMA1Strategy
from .strategy_vwema1 import VWEMA1Strategy


def build_snapshot_strategies():
    return [EMA1Strategy(), EMA2Strategy(), EMA3Strategy(), SMA1Strategy(), VWEMA1Strategy()]
