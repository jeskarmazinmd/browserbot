"""Registry for independently removable strategy modules."""
from . import strategy_tf1
from . import strategy_bo1
from . import strategy_or1
from . import strategy_rs1
from . import strategy_rs2
from . import strategy_ve1
from . import strategy_rs3
from . import strategy_mc1
from . import strategy_tl1
from . import strategy_av1
from . import strategy_td1
from . import strategy_sh1
from . import strategy_cv1
from . import strategy_hl1
from . import strategy_vt1
from . import strategy_pd1
from . import strategy_m1
from . import strategy_m2
from . import strategy_m3
from . import strategy_vr1
from . import strategy_ema1
from . import strategy_ema2
from . import strategy_ema3
from . import strategy_sma1
from . import strategy_vwema1

ENABLED_STRATEGIES = [
    strategy_tf1,
    strategy_bo1,
    strategy_or1,
    strategy_rs1,
    strategy_rs2,
    strategy_ve1,
    strategy_rs3,
    strategy_mc1,
    strategy_tl1,
    strategy_av1,
    strategy_td1,
    strategy_sh1,
    strategy_cv1,
    strategy_hl1,
    strategy_vt1,
    strategy_pd1,
    strategy_m1,
    strategy_m2,
    strategy_m3,
    strategy_vr1,
    strategy_ema1,
    strategy_ema2,
    strategy_ema3,
    strategy_sma1,
    strategy_vwema1
]

def evaluate_all(context):
    signals=[]
    errors=[]
    for module in ENABLED_STRATEGIES:
        try:
            signals.extend(module.evaluate(context))
        except Exception as exc:
            errors.append((module.STRATEGY_ID, exc))
    return signals, errors
