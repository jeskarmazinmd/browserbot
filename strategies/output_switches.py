"""Independent, reloadable controls for prospective paper outputs.

Signal producers continue evaluating so a disabled source cannot silence a
different enabled strategy that derives its signal from the same market setup.
"""

import json
import os
from pathlib import Path

# Paused after the September 21-23 independent bid/ask paper review.
# Keep source signals and historical ledgers; suppress only new paper entries
# and active performance ranking. IDs here omit the reporting-only BA suffix.
PAUSED_BIDASK_PAPER_IDS = frozenset("""
C3F_R1DN C3N25A20 B C3MG_4OF4 C3N25T60 C3N25A05 C1F1R65
C3MG_BRD30 C2 C2T35 C3N25W30 C2T9 C3MG_XS3 C1F1PB15
C3MG_I5S C3N25S10NH015 C3N25T15 C3MG_P10 C3F_HI10
C3MG_BSLP5 C3L25D20 C3N25S10NH015DUP C3MG_P10S C3N25A10
C3MG_M5S C3MG_SPY5 C3MG_I15S C3MG_QQQ5 C1 C3MG_MED10
C3N50 C3MG_M5L C3N25S10NH020 C3F_R2DN C3N40 C3MG_M15S
C3N25S15 C3MG_I15L G C3L25 C3MG_I5L C3N25S10NH025
C3MG_IWM5 C1F1 C3MG_M15L C3N25S10NH005 C3N25
C3N25S10NH040 C3N25S10NH010 J1 C3F_LOW3 C3MG_DSP75
C3F_HI5 C3N25S10NH050 C3MG_3OF4 C3N25S10NH015XWEAK
C3MG_DIV2 C3N25S10NH060 C3MG_P10L C3MG_STRESS
C3MG_NAR50 C3N25S10DUP C3 C3MG_REL20 C3N20 C3MG_2OF4
C3F_HI3 J2T15 C3N25S10NH120 J2RB30 C3N25S10
C3N25S10NH090 J2 J6
""".split())


def output_enabled(strategy_id, path=None):
    strategy_id = str(strategy_id or "").upper()
    # The runner passes base IDs; performance reporting passes base ID + BA.
    # Do not suppress broker execution: that path does not use this function.
    if strategy_id in PAUSED_BIDASK_PAPER_IDS or (
        strategy_id.endswith("BA")
        and strategy_id[:-2] in PAUSED_BIDASK_PAPER_IDS
    ):
        return False
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
    return switches.get(strategy_id, True) is not False
