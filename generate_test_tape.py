from datetime import datetime, timedelta, timezone
import csv

OUT = "replay_test.csv"

def write_rows():
    start = datetime(2026, 8, 2, 13, 30, tzinfo=timezone.utc)
    rows = []

    # AAA: 30 minute rise, 3 minute flash drop, rebound
    price = 100.0
    for i in range(31):
        rows.append([start + timedelta(minutes=i), "AAA", round(price, 4)])
        price += 0.02

    flash_prices = [100.6, 100.0, 99.0, 99.4, 99.8, 100.1]
    for i, p in enumerate(flash_prices, start=31):
        rows.append([start + timedelta(minutes=i), "AAA", p])

    # BBB: clean trend
    price = 50.0
    for i in range(37):
        rows.append([start + timedelta(minutes=i), "BBB", round(price, 4)])
        price += 0.15

    # CCC: noise
    noise = [25.00, 25.02, 24.99, 25.01, 25.00, 25.03]
    for i, p in enumerate(noise):
        rows.append([start + timedelta(minutes=i), "CCC", p])

    rows.sort(key=lambda x: x[0])

    with open(OUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "symbol", "price"])
        for ts, symbol, price in rows:
            writer.writerow([ts.isoformat(), symbol, price])

    print(f"WROTE {OUT} rows={len(rows)}")


if __name__ == "__main__":
    write_rows()
