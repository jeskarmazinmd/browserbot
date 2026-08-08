import gzip
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_lab.cross_symbol import assess_minute_data
from research_lab.discovery import inspect_source
from research_lab.search_space import dimensions


class CrossSymbolResearchTests(unittest.TestCase):
    def test_xs_dimensions_are_first_class(self):
        names={x.name for x in dimensions()}
        expected={
            "cross_symbol_lead_lag",
            "cross_symbol_divergence",
            "cross_symbol_peer_basket",
            "cross_symbol_residual",
            "cross_symbol_regime_adaptation",
        }
        self.assertTrue(expected <= names)

    def test_after_hours_cache_is_fixture_only(self):
        ts=pd.date_range(
            "2026-08-07 22:44:00+00:00",
            periods=76,
            freq="min",
        )
        frame=pd.DataFrame({
            "timestamp":list(ts)*2,
            "symbol":["AAA"]*76+["BBB"]*76,
            "price":[100.0]*152,
        })
        result=assess_minute_data(
            frame,
            min_regular_minutes=300,
            min_symbols=2,
        )
        self.assertEqual(result.state,"FIXTURE_ONLY")
        self.assertEqual(result.regular_minutes,0)

    def test_full_regular_session_can_be_eligible(self):
        ts=pd.date_range(
            "2026-08-10 13:30:00+00:00",
            periods=390,
            freq="min",
        )
        frame=pd.DataFrame({
            "timestamp":list(ts)*2,
            "symbol":["AAA"]*390+["BBB"]*390,
            "price":[100.0]*780,
        })
        result=assess_minute_data(
            frame,
            min_regular_minutes=300,
            min_symbols=2,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.regular_minutes,390)

    def test_rich_compressed_minute_archive_is_discovered(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"minute_market_quotes_20260810.csv.gz"
            with gzip.open(path,"wt") as f:
                f.write(
                    "market_minute_utc,observed_at_utc,symbol,last,bid,ask\n"
                    "2026-08-10T13:30:00+00:00,"
                    "2026-08-10T13:30:59+00:00,"
                    "XYZ,100,99.9,100.1\n"
                )

            spec=inspect_source(path)
            self.assertEqual(spec.format,"csv.gz")
            self.assertIn("minute_market_data",spec.roles)
            self.assertIn("bid",spec.fields)
            self.assertIn("ask",spec.fields)


if __name__=="__main__":
    unittest.main()
