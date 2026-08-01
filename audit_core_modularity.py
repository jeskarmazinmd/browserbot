"""Structural checks for the modular strategy architecture."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE_FILES = [
    ROOT / "live_strategy_runner.py",
    ROOT / "leaderboard_writer.py",
    ROOT / "live_quote_collector.py",
    ROOT / "bot_output.py",
]

# These implementations must never reappear in process entry points.
FORBIDDEN_FUNCTIONS = {
    "strategy_c_signal_paper_outcome_lines",
    "strategy_j_signal_paper_outcome_lines",
    "strategy_k_family_lines",
    "strategy_dynamic_variant_lines",
}

errors: list[str] = []
for path in CORE_FILES:
    tree = ast.parse(path.read_text(), filename=str(path))
    functions = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    leaked = sorted(functions & FORBIDDEN_FUNCTIONS)
    if leaked:
        errors.append(f"{path.name}: leaked reporting strategy engines {leaked}")

# The writer and collector must remain very small / infrastructure-only.
if len((ROOT / "leaderboard_writer.py").read_text().splitlines()) > 40:
    errors.append("leaderboard_writer.py is no longer a thin entry point")

from strategies.manifest import STRATEGY_MANIFEST

required = {
    "A", "B", "C1", "C2", "C3", "C4", "D", "E", "F", "G", "H", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
    "TF1", "BO1", "OR1", "RS1", "RS2", "RS3", "VE1", "VR1",
    "M1", "M2", "M3", "MC1", "TL1", "AV1", "TD1", "SH1", "CV1",
    "HL1", "VT1", "PD1", "EMA1", "EMA2", "EMA3", "SMA1", "VWEMA1",
}
missing = sorted(required - set(STRATEGY_MANIFEST))
if missing:
    errors.append(f"missing strategy modules: {missing}")

for strategy_id, record in STRATEGY_MANIFEST.items():
    if not record.description:
        errors.append(f"{strategy_id}: missing description")
    if not isinstance(record.config, dict):
        errors.append(f"{strategy_id}: CONFIG is not a dict")

if errors:
    raise SystemExit("\n".join(errors))
print(f"modularity audit passed: {len(STRATEGY_MANIFEST)} strategy modules discovered")
