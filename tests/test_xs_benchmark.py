import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research_lab.xs_benchmark import (
    COMPUTE_ONLY,
    benchmark_minute_cache,
    load_minute_cache,
)


class XSBenchmarkTests(unittest.TestCase):
    def test_benchmark_is_explicitly_compute_only(self):
        rng=np.random.default_rng(5)
        times=pd.date_range(
            "2026-08-03 22:44:00+00:00",periods=40,freq="min"
        )
        rows=[]
        for symbol in ("A","B","C","D"):
            prices=100*np.cumprod(1+rng.normal(0,.002,len(times)))
            rows.extend(
                {"timestamp":t,"symbol":symbol,"price":p}
                for t,p in zip(times,prices)
            )
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"minute.pkl"
            pd.DataFrame(rows).to_pickle(path)
            result=benchmark_minute_cache(
                path,lookback=20,horizon=1,repeats=1
            )
        self.assertEqual(result.role,COMPUTE_ONLY)
        self.assertEqual(result.symbols,4)
        self.assertEqual(result.complete_symbols,4)
        self.assertGreaterEqual(result.median_fit_seconds,0)

    def test_rejects_unexpected_pickle_schema(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"bad.pkl"
            pd.DataFrame({"wrong":[1]}).to_pickle(path)
            with self.assertRaisesRegex(ValueError,"unexpected minute-cache schema"):
                load_minute_cache(path)


if __name__=="__main__":
    unittest.main()
