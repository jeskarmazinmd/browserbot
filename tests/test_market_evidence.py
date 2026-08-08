import csv
import gzip
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone

from market_evidence import MinuteMarketArchive
from market_quotes import extract_quote_snapshot


def snap(last,bid,ask):
    return extract_quote_snapshot("XYZ",{
        "realtime":True,
        "quote":{
            "lastPrice":last,
            "bidPrice":bid,
            "askPrice":ask,
            "bidSize":100,
            "askSize":80,
            "quoteTime":1,
        },
    })


class MinuteMarketArchiveTests(unittest.TestCase):
    def test_keeps_final_snapshot_of_completed_market_minute(self):
        with tempfile.TemporaryDirectory() as root:
            a=MinuteMarketArchive(root)

            a.update(
                datetime(2026,8,10,13,30,5,tzinfo=timezone.utc),
                {"XYZ":snap(100,99.9,100.1)},
                True,
            )
            a.update(
                datetime(2026,8,10,13,30,59,tzinfo=timezone.utc),
                {"XYZ":snap(101,100.9,101.1)},
                True,
            )
            a.update(
                datetime(2026,8,10,13,31,1,tzinfo=timezone.utc),
                {"XYZ":snap(102,101.9,102.1)},
                True,
            )

            path=Path(root)/"minute_market_quotes_20260810.csv.gz"
            with gzip.open(path,"rt",newline="") as f:
                rows=list(csv.DictReader(f))

            self.assertEqual(len(rows),1)
            self.assertEqual(float(rows[0]["last"]),101)
            self.assertEqual(float(rows[0]["bid"]),100.9)
            self.assertEqual(float(rows[0]["ask"]),101.1)

    def test_closed_market_minute_is_not_archived(self):
        with tempfile.TemporaryDirectory() as root:
            a=MinuteMarketArchive(root)
            a.update(
                datetime(2026,8,10,12,0,tzinfo=timezone.utc),
                {"XYZ":snap(100,99.9,100.1)},
                False,
            )
            a.close()
            self.assertEqual(list(Path(root).glob("*.gz")),[])


if __name__=="__main__":
    unittest.main()
