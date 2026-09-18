"""Independent, reloadable controls for prospective paper outputs.

Signal producers continue evaluating so a disabled source cannot silence a
different enabled strategy that derives its signal from the same market setup.
"""

import json
import os
from pathlib import Path


def output_enabled(strategy_id, path=None):
    path = Path(path or os.environ.get(
        "STRATEGY_OUTPUT_SWITCHES_PATH", "/data/strategy_output_switches.json"
    ))
    try:
        switches = json.loads(path.read_text())
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        # A malformed control file must not silently disable every strategy.
        return True
    if not isinstance(switches, dict):
        return True
    return switches.get(str(strategy_id).upper(), True) is not False
