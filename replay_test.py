from pathlib import Path
import quote_source

quote_source._TAPE_PATH = Path("quotes_20260731.csv")

df = quote_source.read_data()

print("ROWS:", len(df))
print("COLUMNS:", list(df.columns))
print()
print(df.head())
print()
print("SYMBOLS:", df["symbol"].nunique())
print("TIME RANGE:")
print(df["timestamp"].min())
print(df["timestamp"].max())

print()
print("✓ replay quote source works")
