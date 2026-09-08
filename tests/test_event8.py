import importlib,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import event_shadow_worker as worker
class Event8Tests(unittest.TestCase):
    def test_modules_are_independent_and_safe(self):
        self.assertGreater(len(worker.STRATEGIES),0)
        self.assertLessEqual(len(worker.STRATEGIES),8)
        for sid in worker.STRATEGIES:
            m=importlib.import_module(f"event_strategies.strategy_{sid.lower()}")
            self.assertTrue(m.PAPER_ONLY);self.assertFalse(m.LIVE_ORDER_PLACEMENT);self.assertNotIn("strategy_common",Path(m.__file__).read_text())
    def test_causality_validation(self):
        now=datetime.now(timezone.utc);row={"event_id":"x","published_at":now.isoformat(),"observed_at":(now-timedelta(seconds=1)).isoformat(),"symbol":"SPY","event_type":"MACRO_RELEASE","direction":"POSITIVE","source":"test","source_url":"https://example.test/x"}
        self.assertEqual(worker.validate(row,now)[1],"causality_violation")
    def test_requires_verifiable_provenance(self):
        now=datetime.now(timezone.utc);row={"event_id":"x","published_at":now.isoformat(),"observed_at":now.isoformat(),"symbol":"SPY","event_type":"MACRO_RELEASE","direction":"POSITIVE","source":"test","source_url":"unknown"}
        self.assertEqual(worker.validate(row,now)[1],"unverifiable_source")
    def test_no_broker_or_trading_client(self):
        source=Path(worker.__file__).read_text();self.assertNotIn("place_order",source);self.assertNotIn("trading_client",source)
if __name__=="__main__":unittest.main()


class EventBidAskV2Tests(unittest.TestCase):
    def _quote(self,now,bid=99.9,ask=100.0,bid_size=100,ask_size=100):
        ms=int(now.timestamp()*1000)
        return {
            "symbol":"AAA",
            "bid":bid,
            "ask":ask,
            "realtime":True,
            "bid_time_ms":ms,
            "ask_time_ms":ms,
            "quote_time_ms":ms,
            "bid_size_raw":bid_size,
            "ask_size_raw":ask_size,
        }

    def _decision(self,now,side="LONG"):
        return {
            "strategy_id":"X",
            "event_id":"E1",
            "symbol":"AAA",
            "side":side,
            "timestamp":now.isoformat(),
            "published_at":now.isoformat(),
            "source":"test",
            "entry_bid":1.0,
            "entry_ask":1.01 if side=="LONG" else 100.0,
            "hold_minutes":1,
            "target_fraction":0.50,
            "stop_fraction":0.50,
        }

    def test_v2_paths_and_execution_model(self):
        from event_paper_tracker import EventPaperTracker
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            self.assertEqual(t.ledger.name,"event_paper_v2_bidask_outcomes.jsonl")
            self.assertEqual(t.status_path.name,"event_paper_v2_bidask_status.json")
            import json
            status=json.loads(t.status_path.read_text())
            self.assertEqual(status["execution_model"],"BIDASK_EXEC_V1")

    def test_execution_uses_separate_quote_not_signal_price(self):
        from event_paper_tracker import EventPaperTracker
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            q=self._quote(now,ask=100.0)
            self.assertTrue(t.register(d,q))
            row=next(iter(t.active.values()))
            self.assertEqual(row["entry_price"],100.0)
            self.assertEqual(row["shares"],10)
            self.assertEqual(row["execution"]["price_source"],"ASK")

    def test_stale_entry_is_unknown_and_consumes_event(self):
        from event_paper_tracker import EventPaperTracker
        import json
        now=datetime.now(timezone.utc)
        stale=now-timedelta(seconds=5)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            self.assertFalse(t.register(d,self._quote(stale)))
            rows=[json.loads(x) for x in t.ledger.read_text().splitlines()]
            self.assertEqual(rows[-1]["event"],"OPEN_ATTEMPT")
            self.assertEqual(rows[-1]["execution"]["outcome"],"UNKNOWN")
            self.assertFalse(t.register(d,self._quote(now)))

    def test_partial_entry_owns_only_fill(self):
        from event_paper_tracker import EventPaperTracker
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            self.assertTrue(t.register(d,self._quote(now,ask_size=4)))
            row=next(iter(t.active.values()))
            self.assertEqual(row["requested_shares"],10)
            self.assertEqual(row["shares"],4)
            self.assertEqual(row["execution"]["outcome"],"PARTIAL")



    def test_missing_execution_quote_is_unknown(self):
        from event_paper_tracker import EventPaperTracker
        import json
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            self.assertFalse(t.register(d,None))
            rows=[json.loads(x) for x in t.ledger.read_text().splitlines()]
            self.assertEqual(rows[-1]["event"],"OPEN_ATTEMPT")
            self.assertEqual(rows[-1]["execution"]["outcome"],"UNKNOWN")
            self.assertEqual(rows[-1]["execution"]["reason"],"MISSING_EXECUTION_QUOTE")
            self.assertEqual(len(t.active),0)

    def test_short_entry_executes_at_bid(self):
        from event_paper_tracker import EventPaperTracker
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now,side="SHORT")
            d["entry_bid"]=100.0
            q=self._quote(now,bid=100.0,ask=100.1)
            self.assertTrue(t.register(d,q))
            row=next(iter(t.active.values()))
            self.assertEqual(row["entry_price"],100.0)
            self.assertEqual(row["execution"]["action"],"SELL")
            self.assertEqual(row["execution"]["price_source"],"BID")

    def test_long_exit_executes_at_bid(self):
        from event_paper_tracker import EventPaperTracker
        import json
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            d["hold_minutes"]=1
            self.assertTrue(t.register(d,self._quote(now,bid=99.9,ask=100.0)))
            later=now+timedelta(minutes=2)
            self.assertEqual(
                t.update(later,{"AAA":self._quote(later,bid=99.8,ask=99.9)}),
                1,
            )
            rows=[json.loads(x) for x in t.ledger.read_text().splitlines()]
            close=rows[-1]
            self.assertEqual(close["event"],"CLOSE")
            self.assertEqual(close["exit_price"],99.8)
            self.assertEqual(close["execution"]["action"],"SELL")
            self.assertEqual(close["execution"]["price_source"],"BID")
            self.assertTrue(close["position_closed"])

    def test_short_exit_executes_at_ask(self):
        from event_paper_tracker import EventPaperTracker
        import json
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now,side="SHORT")
            d["entry_bid"]=100.0
            d["hold_minutes"]=1
            self.assertTrue(t.register(d,self._quote(now,bid=100.0,ask=100.1)))
            later=now+timedelta(minutes=2)
            self.assertEqual(
                t.update(later,{"AAA":self._quote(later,bid=100.1,ask=100.2)}),
                1,
            )
            rows=[json.loads(x) for x in t.ledger.read_text().splitlines()]
            close=rows[-1]
            self.assertEqual(close["event"],"CLOSE")
            self.assertEqual(close["exit_price"],100.2)
            self.assertEqual(close["execution"]["action"],"BUY")
            self.assertEqual(close["execution"]["price_source"],"ASK")

    def test_partial_exit_keeps_residual_position(self):
        from event_paper_tracker import EventPaperTracker
        import json
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            t=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            d["hold_minutes"]=1
            self.assertTrue(t.register(d,self._quote(now,bid=99.9,ask=100.0)))
            later=now+timedelta(minutes=2)
            self.assertEqual(
                t.update(
                    later,
                    {"AAA":self._quote(later,bid=99.8,ask=99.9,bid_size=4)},
                ),
                0,
            )
            self.assertEqual(len(t.active),1)
            row=next(iter(t.active.values()))
            self.assertEqual(row["shares"],6)
            rows=[json.loads(x) for x in t.ledger.read_text().splitlines()]
            close=rows[-1]
            self.assertEqual(close["event"],"CLOSE")
            self.assertEqual(close["shares"],4)
            self.assertEqual(close["remaining_shares"],6)
            self.assertFalse(close["position_closed"])

            restarted=EventPaperTracker(root)
            self.assertEqual(len(restarted.active),1)
            restored=next(iter(restarted.active.values()))
            self.assertEqual(restored["shares"],6)
    def test_restart_restores_active_and_seen(self):
        from event_paper_tracker import EventPaperTracker
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            a=EventPaperTracker(root)
            d=self._decision(now)
            d["entry_ask"]=100.0
            self.assertTrue(a.register(d,self._quote(now)))
            b=EventPaperTracker(root)
            self.assertEqual(len(b.active),1)
            self.assertEqual(len(b.seen),1)
            self.assertFalse(b.register(d,self._quote(now)))
