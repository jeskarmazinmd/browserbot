from datetime import datetime, timedelta, timezone
import csv
import random

OUT = "fake_flash_dip_test.csv"

start = datetime(
    2026, 7, 31, 14, 0, 0,
    tzinfo=timezone.utc
)

rows = []

def add_quote(t, symbol, price):
    rows.append([
        t.isoformat(),
        symbol,
        round(price, 4)
    ])

symbol = "TEST"

# -----------------------------
# 30 minute healthy uptrend
# -----------------------------
t = start
price = 100.0

for i in range(30 * 60 // 5):
    price += 0.002
    add_quote(t, symbol, price)
    t += timedelta(seconds=5)


# -----------------------------
# Flash crash over 3 minutes
# -----------------------------
for i in range(36):
    price -= 0.05
    add_quote(t, symbol, price)
    t += timedelta(seconds=5)


# -----------------------------
# Rebound
# -----------------------------
for i in range(36):
    price += 0.015
    add_quote(t, symbol, price)
    t += timedelta(seconds=5)


# -----------------------------
# Continue higher
# -----------------------------
for i in range(60):
    price += 0.01
    add_quote(t, symbol, price)
    t += timedelta(seconds=5)


with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "timestamp_utc",
        "symbol",
        "last_price"
    ])
    w.writerows(rows)

print(f"wrote {len(rows)} rows")
print(f"start={rows[0][0]}")
print(f"end={rows[-1][0]}")
