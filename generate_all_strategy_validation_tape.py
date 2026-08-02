from datetime import datetime, timedelta, timezone
import csv

OUT = "all_strategy_validation.csv"


def add(rows, t, symbol, price, volume=1000):
    rows.append([
        t.isoformat(),
        symbol,
        round(price, 4),
        volume,
    ])


def write_rows():
    start = datetime(2026, 8, 2, 13, 30, tzinfo=timezone.utc)

    rows = []

    # ============================================================
    # AAA: FLASH REBOUND
    # Tests: A / B / D / H
    # ============================================================
    t = start
    prices = [
        100.0,
        100.1,
        100.2,
        100.3,
        99.0,   # -1.3% drop
        99.3,   # +0.3% rebound
        99.5,
    ]

    for i, p in enumerate(prices):
        add(rows, t + timedelta(minutes=i), "AAA", p)


    # ============================================================
    # BBB: CLEAN TREND
    # Tests: EMA3 / SMA1 / VWEMA1
    # ============================================================
    t = start

    price = 50.0
    for i in range(45):
        add(rows, t + timedelta(minutes=i), "BBB", price)
        price += 0.15


    # ============================================================
    # CCC: EMA PULLBACK AND RECLAIM
    # Tests: EMA2
    # ============================================================
    t = start

    prices = [
        100.0,
        100.15,
        100.30,
        100.45,
        100.60,
        100.75,
        100.65,
        100.55,   # pullback
        100.70,   # bounce
        100.85,
    ]

    for i, p in enumerate(prices):
        add(rows, t + timedelta(minutes=i), "CCC", p)


    # ============================================================
    # DDD: TREND + VOLUME EXPANSION
    # Tests: EMA1 / TF1
    # ============================================================
    t = start

    price = 200.0

    for i in range(35):
        vol = 1000

        # create volume expansion near crossover
        if i >= 30:
            vol = 3000

        add(
            rows,
            t + timedelta(minutes=i),
            "DDD",
            price,
            vol
        )

        price += 0.08


    # ============================================================
    # EEE: NOISE CONTROL
    # Should not create trend signals
    # ============================================================
    t = start

    noise = [
        25.00,
        25.02,
        24.99,
        25.01,
        25.00,
        25.03,
        25.01,
        25.02,
    ]

    for i, p in enumerate(noise):
        add(rows, t + timedelta(minutes=i), "EEE", p)


    rows.sort(key=lambda x: x[0])

    with open(OUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "symbol",
            "price",
            "total_volume",
        ])

        writer.writerows(rows)

    print(f"WROTE {OUT} rows={len(rows)}")


if __name__ == "__main__":
    write_rows()
