import os,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
import sec_event_adapter as sec
class SecAdapterTests(unittest.TestCase):
    def test_requires_declared_user_agent(self):
        old=sec.USER_AGENT;sec.USER_AGENT=""
        try:
            with self.assertRaisesRegex(RuntimeError,"SEC_USER_AGENT"):sec._get("https://www.sec.gov/")
        finally:sec.USER_AGENT=old
    def test_atom_preserves_official_time_and_unknown_direction(self):
        xml=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>8-K - Example (0000123456)</title><updated>2026-08-09T18:00:00-04:00</updated><link href="https://www.sec.gov/Archives/edgar/data/123456/x-index.html"/><summary>CIK 123456</summary></entry></feed>'''
        rows=sec.parse_atom(xml,{"123456":"TEST"},datetime.now(timezone.utc));self.assertEqual(len(rows),1);self.assertEqual(rows[0]["direction"],"UNKNOWN");self.assertEqual(rows[0]["published_at"],"2026-08-09T18:00:00-04:00")
    def test_no_broker_calls(self):
        source=Path(sec.__file__).read_text();self.assertNotIn("place_order",source);self.assertNotIn("trading_client",source)
    def test_strategy_uses_prospective_reaction(self):
        from event_strategies.strategy_evtsec8k1 import Strategy
        event={"event_id":"e","event_type":"SEC_8K","symbol":"TEST","published_at":"2026-08-09T18:00:00+00:00","source":"SEC","reaction_minutes":5,"reaction_return":0.01};quote={"bid":10,"ask":10.01}
        self.assertEqual(Strategy().evaluate(event,quote)[0]["side"],"LONG")
if __name__=="__main__":unittest.main()
