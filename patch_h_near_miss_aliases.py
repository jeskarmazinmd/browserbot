#!/usr/bin/env python3
"""Patch the current runner without replacing it.

Adds Strategy H near-miss aliases sourced from the module-owned configuration.
Safe to run repeatedly.
"""
from pathlib import Path

path = Path(__file__).resolve().parent / "live_strategy_runner.py"
if not path.exists():
    raise SystemExit(f"Missing {path}. Run this from the browserbot project root.")
text = path.read_text()
marker = 'STRATEGY_H_MIN_FLASH_DROP_PCT = STRATEGY_CONFIGS[STRATEGY_H]["flash_drop_pct"]'
if marker in text:
    print("Strategy H near-miss aliases already present")
    raise SystemExit(0)
needle = 'STRATEGY_H = "H"\n'
if needle not in text:
    raise SystemExit("Could not find STRATEGY_H declaration; no changes made")
block = '''STRATEGY_H = "H"\n\n# Strategy H near-miss aliases derived from the module-owned configuration.\n# These preserve the existing near-miss calculations without duplicating rules.\nSTRATEGY_H_MIN_FLASH_DROP_PCT = STRATEGY_CONFIGS[STRATEGY_H]["flash_drop_pct"]\nSTRATEGY_H_MAX_FLASH_DROP_PCT = STRATEGY_CONFIGS[STRATEGY_H]["max_flash_drop_pct"]\nSTRATEGY_H_MIN_PRE_R2 = STRATEGY_CONFIGS[STRATEGY_H]["min_pre_r2"]\nSTRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR = STRATEGY_CONFIGS[STRATEGY_H]["max_pre_slope_pct_per_hour"]\n'''
path.write_text(text.replace(needle, block, 1))
print("Patched live_strategy_runner.py Strategy H near-miss aliases")
