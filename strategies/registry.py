from . import strategy_a
from . import strategy_b
from . import strategy_d
from . import strategy_h

FLASH_STRATEGY_MODULES = {
    module.STRATEGY_ID: module
    for module in (strategy_a, strategy_b, strategy_d, strategy_h)
}

def flash_strategy_configs():
    return {strategy_id: dict(module.CONFIG) for strategy_id, module in FLASH_STRATEGY_MODULES.items()}

def flash_accepts(strategy_id, event, global_max_drop_pct):
    return FLASH_STRATEGY_MODULES[strategy_id].accepts_flash(event, global_max_drop_pct)

def refresh_flash_entry(strategy_id, event, current_price):
    return FLASH_STRATEGY_MODULES[strategy_id].refresh_event_for_entry(event, current_price)

def validate_flash_entry(strategy_id, event, default_min_remaining_upside_pct):
    module = FLASH_STRATEGY_MODULES[strategy_id]
    try:
        return module.validate_confirmed_entry(event, default_min_remaining_upside_pct)
    except TypeError:
        return module.validate_confirmed_entry(event)

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

# Paper/reporting-only variants. They are intentionally not included in
# ENABLED_STRATEGIES because they consume parent strategy events rather than
# scanning quotes directly.
REPORTING_STRATEGY_MODULES = {}
for _strategy_id in (
    "C1", "C2", "C3", "C4", "E", "F", "G", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
):
    _module = __import__(f"strategies.strategy_{_strategy_id.lower()}", fromlist=["*"])
    REPORTING_STRATEGY_MODULES[_strategy_id] = _module
