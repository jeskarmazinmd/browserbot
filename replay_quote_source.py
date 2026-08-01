from pathlib import Path
import pandas as pd


class ReplayQuoteSource:
    def __init__(self, tape_path):
        self.tape_path = Path(tape_path)
        self._data = None

    def read_data(self):
        if self._data is not None:
            return self._data

        df = pd.read_csv(
            self.tape_path,
            names=["timestamp", "symbol", "price"],
            header=0,
            low_memory=False,
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
            errors="coerce",
        )

        df["price"] = pd.to_numeric(
            df["price"],
            errors="coerce",
        )

        df = df.dropna(
            subset=["timestamp", "symbol", "price"]
        )

        self._data = df

        return df

    def now(self):
        return self.read_data()["timestamp"].max()
