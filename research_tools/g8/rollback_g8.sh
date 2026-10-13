#!/usr/bin/env bash
set -euo pipefail
# Keep the G8-compatible image and service all residual exits. This changes
# only the two new opt-in flags; no existing broker secret is touched.
fly secrets set ENABLE_G8_PAPER=0 ENABLE_G8_RETIREMENTS=0 -a schwab
fly ssh console -a schwab --machine 7813422f149398 -C 'python -c "import json,pathlib; p=pathlib.Path(\"/data/paper_generation_eight_bidask_independent_status.json\"); print(p.read_text()); from strategies.registry import G8_ENABLED; from strategies.generation_eight_retirement import report_ids; assert not G8_ENABLED; assert not report_ids()"'
echo 'G8 entries disabled, previous output gates restored, compatible residual-exit tracker retained.'
echo 'Do not revert to the pre-G8 binary while G8 residual positions remain.'
