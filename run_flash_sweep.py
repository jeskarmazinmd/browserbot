import re
import shutil
import subprocess
from pathlib import Path
import pandas as pd

BASE = Path("full_parameter_research.py")
WORK = Path("full_parameter_research_tmp_sweep.py")
OUT = Path("flash_threshold_sweep_results.csv")

thresholds = [round(x / 10, 1) for x in range(15, 26)]
rows = []

for t in thresholds:
    print(f"\n===== RUNNING FLASH_DROP_PCT={t:.1f} =====", flush=True)

    s = BASE.read_text()
    s = re.sub(r"^FLASH_DROP_PCT\\s*=\\s*[0-9.]+", f"FLASH_DROP_PCT = {t:.1f}", s, flags=re.M)
    s = re.sub(
        r'^INPUT_FILE\\s*=.*$',
        'INPUT_FILE = Path("1Mvolumesymbols.csv")',
        s,
        flags=re.M,
    )

    # make output file names unique if script uses timestamp less reliably
    WORK.write_text(s)

    proc = subprocess.run(
        ["scannerenv/bin/python", str(WORK)],
        capture_output=True,
        text=True,
    )

    output = proc.stdout + "\n" + proc.stderr
    print(output[-3000:], flush=True)

    def grab(pattern, default=None, cast=float):
        m = re.search(pattern, output)
        if not m:
            return default
        try:
            return cast(m.group(1).replace(",", ""))
        except Exception:
            return default

    rows.append({
        "flash_drop_pct": t,
        "returncode": proc.returncode,
        "trades": grab(r"Trades found:\s*([0-9,]+)", 0, int),
        "total_pnl": grab(r"Total simulated P/L:\s*\$?([-0-9,.]+)", 0.0, float),
        "avg_pnl": grab(r"Average P/L per trade:\s*\$?([-0-9,.]+)", 0.0, float),
        "median_pnl": grab(r"Median P/L per trade:\s*\$?([-0-9,.]+)", 0.0, float),
        "avg_return_pct": grab(r"Average return per trade:\s*([-0-9.]+)%", 0.0, float),
        "median_return_pct": grab(r"Median return per trade:\s*([-0-9.]+)%", 0.0, float),
        "win_rate_pct": grab(r"Win rate:\s*([-0-9.]+)%", 0.0, float),
    })

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Saved partial results to {OUT}", flush=True)

if WORK.exists():
    WORK.unlink()

print("\n===== FINAL SWEEP RESULTS =====")
df = pd.DataFrame(rows)
print(df.to_string(index=False))
df.to_csv(OUT, index=False)
print(f"\nSaved final results to {OUT.resolve()}")
