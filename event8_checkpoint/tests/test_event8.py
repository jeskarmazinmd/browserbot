import importlib,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import event_shadow_worker as worker
class Event8Tests(unittest.TestCase):
    def test_modules_are_independent_and_safe(self):
        self.assertEqual(len(worker.STRATEGIES),8)
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
