from pathlib import Path
from datetime import timedelta
import os
import pandas as pd


class ReplayQuoteSource:
    def __init__(self, tape_path, step_seconds=None):
        self.tape_path = Path(tape_path)
        if step_seconds is None:
            step_seconds = int(os.environ.get("REPLAY_SPEED", "60"))
        self.step = timedelta(seconds=step_seconds)
        self._data = None
        self._cursor_time = None

    def _load(self):
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

        df = df.sort_values("timestamp")

        self._data = df
        self._cursor_time = df["timestamp"].min()

    def read_data(self):
        if self._data is None:
            self._load()
        else:
            self._cursor_time += self.step

        return self._data[
            self._data["timestamp"] <= self._cursor_time
        ]

    def now(self):
        if self._cursor_time is None:
            self._load()

        return self._cursor_time
