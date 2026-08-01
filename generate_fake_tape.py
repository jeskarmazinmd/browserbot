from datetime import datetime, timedelta, timezone
import csv

OUT = "fake_quotes.csv"

start = datetime(2026, 7, 31, 14, 0, 0, tzinfo=timezone.utc)  # 10:00 ET

rows = []

def add_minute(t, symbol, price):
    rows.append([
        t.isoformat(),
        symbol,
        round(price, 4)
    ])

# Symbol to test
sym = "TEST"

price = 100.0

# 30 minute rising trend
for i in range(30):
    add_minute(
        start + timedelta(minutes=i),
        sym,
        100 + i * 0.05
    )

# Flash drop (~1.5%)
drop_start = start + timedelta(minutes=30)

for i, p in enumerate([
    101.50,
    100.80,
    100.00,
]):
    add_minute(
        drop_start + timedelta(minutes=i),
        sym,
        p
    )

# Rebound
for i, p in enumerate([
    100.20,
    100.50,
    100.80,
    101.00,
]):
    add_minute(
        drop_start + timedelta(minutes=3+i),
        sym,
        p
    )

# Continue
for i in range(10):
    add_minute(
        drop_start + timedelta(minutes=7+i),
        sym,
        101.0 + i*0.1
    )

with open(OUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "timestamp_utc",
        "symbol",
        "last_price"
    ])
    writer.writerows(rows)

print(f"wrote {len(rows)} rows to {OUT}")
