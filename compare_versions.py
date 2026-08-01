import subprocess
import time

def run(cmd):
    start = time.time()
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return time.time() - start, out.stdout + out.stderr

print("\n===== RUNNING V22 =====\n")
t1, out1 = run("python3 trendline_scanner_v22.py")

print("\n===== RUNNING V25 =====\n")
t2, out2 = run("python3 trendline_scanner_v25_live_schwab.py")

print("\n===== SUMMARY =====\n")
print(f"V22 runtime: {t1:.2f}s")
print(f"V25 runtime: {t2:.2f}s")

print("\n--- V22 OUTPUT (last 30 lines) ---")
print("\n".join(out1.splitlines()[-30:]))

print("\n--- V25 OUTPUT (last 30 lines) ---")
print("\n".join(out2.splitlines()[-30:]))
