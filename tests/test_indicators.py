from engine.indicators import ema, sma

prices = list(range(1, 31))

print("SMA5:", sma(prices, 5))
print("EMA9:", round(ema(prices, 9), 4))
