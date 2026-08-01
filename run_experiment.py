import subprocess
import sys

VERSION = sys.argv[1]  # v22 or v25

if VERSION == "v22":
    cmd = "python3 experiments/v22/trendline_scanner_v22.py"
elif VERSION == "v25":
    cmd = "python3 experiments/v25/trendline_scanner_v25_live_schwab.py"
else:
    raise ValueError("Use v22 or v25")

print(f"\nRunning {VERSION}\n")

subprocess.run(cmd, shell=True)
