"""Isolated registry for the generic research family.

Kept separate from strategies.registry so existing strategies remain untouched.
"""
from . import strategy_gt1, strategy_gp1, strategy_gr1, strategy_ge1, strategy_gm1

MODULES = (strategy_gt1, strategy_gp1, strategy_gr1, strategy_ge1, strategy_gm1)


def evaluate_all(context):
    signals, errors = [], []
    for module in MODULES:
        try:
            signal = module.evaluate(context)
            if signal:
                signals.extend(signal if isinstance(signal, list) else [signal])
        except Exception as exc:
            errors.append((getattr(module, "STRATEGY_ID", module.__name__), exc))
    return signals, errors
