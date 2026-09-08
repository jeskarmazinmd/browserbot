import importlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from crosssection_paper_tracker import CrossSectionPaperTracker
from crosssection_shadow_worker import STRATEGIES,_batches,fresh,normalize

class CrossSection8Tests(unittest.TestCase):
    def test_installed_crosssection_modules_are_independent_paper_only(self):
        installed=(
            "CSRANK5INV","CSRANK20INV","CSREV1INV",
            "CSDISP1INV","CSBREADTH1INV","CSRELSPY1INV",
        )
        self.assertEqual(len(set(installed)),len(installed))
        self.assertTrue(set(STRATEGIES).issubset(set(installed)))
        for sid in installed:
            m=importlib.import_module(f"crosssection_strategies.strategy_{sid.lower()}")
            self.assertTrue(m.PAPER_ONLY,sid)
            self.assertFalse(m.LIVE_ORDER_PLACEMENT,sid)
            src=Path(m.__file__).read_text()
            self.assertNotIn("from crosssection_strategies",src,sid)
            self.assertNotIn("import crosssection_strategies",src,sid)
            self.assertNotIn("place_order",src,sid)

    def test_batches_respect_schwab_batch_size(self):
        groups=list(_batches([str(i) for i in range(1201)]));self.assertEqual([len(x) for x in groups],[500,500,201])

    def _quote(self,now,bid=99.9,ask=100.0,bid_size=100,ask_size=100,**extra):
        ms=int(now.timestamp()*1000)
        q={
            "realtime":True,
            "bid":bid,
            "ask":ask,
            "bid_size_raw":bid_size,
            "ask_size_raw":ask_size,
            "bid_time_ms":ms,
            "ask_time_ms":ms,
            "quote_time_ms":ms,
        }
        q.update(extra)
        return q

    def test_normalize_and_fresh(self):
        now=datetime(2026,8,10,14,0,tzinfo=timezone.utc);ms=int(now.timestamp()*1000)
        q=normalize("xyz",{"realtime":True,"quote":{
            "bidPrice":10,"askPrice":10.1,
            "bidSize":37,"askSize":42,
            "bidTime":ms-10,"askTime":ms-5,
            "lastPrice":10.05,"closePrice":9.8,"openPrice":10,
            "quoteTime":ms,"totalVolume":1000,
        }})
        self.assertEqual(q["symbol"],"XYZ")
        self.assertEqual(q["close"],9.8)
        self.assertEqual(q["bid_size_raw"],37)
        self.assertEqual(q["ask_size_raw"],42)
        self.assertEqual(q["bid_time_ms"],ms-10)
        self.assertEqual(q["ask_time_ms"],ms-5)
        self.assertTrue(fresh(q,now))
        self.assertFalse(fresh(dict(q,realtime=False),now))

    def test_tracker_long_and_short_cross_the_spread(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            common={"strategy_id":"X","timestamp":now,"target_pct":10,"stop_pct":10,"max_hold_minutes":1}

            long_q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=100)
            short_q=self._quote(now,bid=100,ask=100.1,bid_size=100,ask_size=100)

            t.open_decisions([
                {**common,**long_q,"symbol":"AAA","side":"LONG"},
                {**common,**short_q,"symbol":"BBB","side":"SHORT"},
            ])

            self.assertEqual(len(t.active),2)

            later=now+timedelta(minutes=2)
            t.update(later,{
                "AAA":self._quote(later,bid=101,ask=101.1,bid_size=100,ask_size=100),
                "BBB":self._quote(later,bid=98.9,ask=99,bid_size=100,ask_size=100),
            })

            rows=[json.loads(x) for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()]
            opens=[r for r in rows if r["event"]=="OPEN"]
            closes=[r for r in rows if r["event"]=="CLOSE"]

            self.assertEqual(len(opens),2)
            self.assertEqual(len(closes),2)
            self.assertEqual(opens[0]["execution_model"],"BIDASK_EXEC_V1")
            self.assertEqual(opens[0]["execution"]["price_source"],"ASK")
            self.assertEqual(opens[1]["execution"]["price_source"],"BID")
            self.assertEqual(closes[0]["execution"]["price_source"],"BID")
            self.assertEqual(closes[1]["execution"]["price_source"],"ASK")
            self.assertAlmostEqual(closes[0]["pnl"],10)
            self.assertAlmostEqual(closes[1]["pnl"],10)

    def test_partial_entry_owns_only_filled_quantity(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=4)
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":10,**q}

            self.assertEqual(t.open_decisions([d]),1)
            row=next(iter(t.active.values()))
            self.assertEqual(row["requested_shares"],10)
            self.assertEqual(row["shares"],4)
            self.assertEqual(row["execution"]["outcome"],"PARTIAL")

    def test_partial_exit_leaves_residual_position(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=100)
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":1,**q}
            t.open_decisions([d])

            later=now+timedelta(minutes=2)
            t.update(later,{
                "AAA":self._quote(later,bid=101,ask=101.1,bid_size=3,ask_size=100)
            })

            row=next(iter(t.active.values()))
            self.assertEqual(row["shares"],7)

            rows=[json.loads(x) for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()]
            close=[r for r in rows if r["event"]=="CLOSE"][-1]
            self.assertEqual(close["shares"],3)
            self.assertEqual(close["remaining_shares"],7)
            self.assertFalse(close["position_closed"])

    def test_stale_entry_does_not_fabricate_fill(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            stale=now-timedelta(seconds=5)
            q=self._quote(stale,bid=99.9,ask=100,bid_size=100,ask_size=100)
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":10,**q}

            self.assertEqual(t.open_decisions([d]),0)
            self.assertEqual(len(t.active),0)

            rows=[json.loads(x) for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()]
            self.assertEqual(rows[-1]["event"],"OPEN_ATTEMPT")
            self.assertEqual(rows[-1]["execution"]["outcome"],"UNKNOWN")

    def test_stale_exit_leaves_position_unresolved(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)

            q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=100)
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":1,**q}

            self.assertEqual(t.open_decisions([d]),1)
            self.assertEqual(len(t.active),1)

            later=now+timedelta(minutes=2)
            stale=later-timedelta(seconds=5)

            result=t.update(later,{
                "AAA":self._quote(
                    stale,bid=101,ask=101.1,
                    bid_size=100,ask_size=100,
                )
            })

            self.assertEqual(result,0)
            self.assertEqual(len(t.active),1)
            self.assertEqual(t.completed,0)

            rows=[
                json.loads(x)
                for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()
            ]
            self.assertEqual([r["event"] for r in rows],["OPEN"])

    def test_missing_exit_liquidity_leaves_position_unresolved(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)

            q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=100)
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":1,**q}

            self.assertEqual(t.open_decisions([d]),1)

            later=now+timedelta(minutes=2)
            exit_q=self._quote(
                later,bid=101,ask=101.1,
                bid_size=100,ask_size=100,
            )
            exit_q.pop("bid_size_raw")

            result=t.update(later,{"AAA":exit_q})

            self.assertEqual(result,0)
            self.assertEqual(len(t.active),1)
            self.assertEqual(t.completed,0)

            rows=[
                json.loads(x)
                for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()
            ]
            self.assertEqual(rows[-1]["event"],"CLOSE_ATTEMPT")
            self.assertEqual(rows[-1]["execution"]["outcome"],"UNKNOWN")

    def test_missing_size_does_not_fabricate_fill(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000)
            now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            q=self._quote(now,bid=99.9,ask=100,bid_size=100,ask_size=100)
            q.pop("ask_size_raw")
            d={"strategy_id":"X","timestamp":now,"symbol":"AAA","side":"LONG",
               "target_pct":10,"stop_pct":10,"max_hold_minutes":10,**q}

            self.assertEqual(t.open_decisions([d]),0)
            self.assertEqual(len(t.active),0)

            rows=[json.loads(x) for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines()]
            self.assertEqual(rows[-1]["execution"]["outcome"],"UNKNOWN")

    def test_all_strategies_survive_broad_synthetic_stream(self):
        installed=(
            "CSRANK5INV","CSRANK20INV","CSREV1INV",
            "CSDISP1INV","CSBREADTH1INV","CSRELSPY1INV",
        )
        mods=[importlib.import_module(f"crosssection_strategies.strategy_{s.lower()}").Strategy() for s in installed];start=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
        for minute in range(25):
            quotes={}
            for i in range(120):
                symbol="SPY" if i==0 else f"S{i:03d}";base=50+i*.2;mid=base*(1+(i-60)*minute/1000000)
                quotes[symbol]={"realtime":True,"bid":mid-.01,"ask":mid+.01,"close":base*.995,"open":base,"quote_time_ms":int((start+timedelta(minutes=minute)).timestamp()*1000)}
            snap={"timestamp":start+timedelta(minutes=minute),"quotes":quotes}
            for m in mods:m.evaluate(snap)
        self.assertEqual(len(mods),len(installed))

if __name__=="__main__":unittest.main()
