import sys
import types
import unittest
from unittest.mock import patch

import crosssection_shadow_worker
import event_shadow_worker
with patch.dict(sys.modules, {"requests": types.ModuleType("requests")}):
    import options_shadow_worker
from crosssection_strategies.inverted import InvertedStrategy as EquityInverse
from event_strategies.inverted import InvertedStrategy as EventInverse
from options_strategies.inverted import InvertedStrategy as OptionInverse


class _EquityOriginal:
    def evaluate(self, snapshot):
        return [{"strategy_id":"CONTROL","timestamp":"2026-09-02T14:00:00+00:00","symbol":"ABC","side":"LONG","bid":10,"ask":10.01,"target_pct":1,"stop_pct":1,"max_hold_minutes":5,"research":{}}]


class _EventOriginal:
    def evaluate(self, event, quote):
        return [{"strategy_id":"CONTROL","event_id":"e1","symbol":"ABC","side":"SHORT","timestamp":"2026-09-02T14:00:00+00:00","entry_bid":10,"entry_ask":10.01,"hold_minutes":5,"target_fraction":.01,"stop_fraction":.01}]


class _OptionOriginal:
    def __init__(self, vertical=False): self.vertical=vertical
    def evaluate(self, snapshot):
        legs=[{"symbol":"C100","side":"BUY","bid":2,"ask":2.1,"multiplier":100,"strike":100,"expiration":"2026-09-18","put_call":"CALL"}]
        if self.vertical: legs.append({"symbol":"C102","side":"SELL","bid":1,"ask":1.1,"multiplier":100,"strike":102,"expiration":"2026-09-18","put_call":"CALL"})
        return [{"strategy_id":"CONTROL","timestamp":"2026-09-02T14:00:00+00:00","underlying":"ABC","legs":legs,"take_profit_pct":10,"stop_loss_pct":10,"max_hold_minutes":5,"research":{}}]


def option_snapshot():
    return {"contracts":[
        {"symbol":"P100","putCall":"PUT","expirationDate":"2026-09-18","strikePrice":100,"bid":2.0,"ask":2.1,"multiplier":100,"delta":-.5},
        {"symbol":"P102","putCall":"PUT","expirationDate":"2026-09-18","strikePrice":102,"bid":3.0,"ask":3.1,"multiplier":100,"delta":-.55},
    ]}


class InversionTests(unittest.TestCase):
    def test_failed_parents_remain_disabled_in_workers(self):
        worker_pairs = (
            (crosssection_shadow_worker.STRATEGIES, (
                "CSRANK5", "CSRANK20", "CSREV1", "CSDISP1",
                "CSBREADTH1", "CSRELSPY1",
            )),
            (event_shadow_worker.STRATEGIES, ("EVTSEC8K1", "EVTVOL1")),
            (options_shadow_worker.STRATEGIES, (
                "OPTDIR1", "OPTDIR2", "OPTVERT1", "OPTVERT2",
            )),
        )
        for active, parents in worker_pairs:
            for parent in parents:
                self.assertNotIn(parent, active)
                self.assertIn(f"{parent}INV", active)

    def test_equity_side_flips_and_control_is_immutable(self):
        inverse=EquityInverse(_EquityOriginal,"CONTROLINV")
        row=inverse.evaluate({})[0]
        self.assertEqual((row["strategy_id"],row["side"]),("CONTROLINV","SHORT"))
        self.assertEqual(row["research"]["control_strategy_id"],"CONTROL")

    def test_event_side_flips(self):
        row=EventInverse(_EventOriginal,"EVENTINV").evaluate({}, {})[0]
        self.assertEqual((row["strategy_id"],row["side"]),("EVENTINV","LONG"))

    def test_single_option_uses_opposite_put(self):
        row=OptionInverse(lambda:_OptionOriginal(False),"DIRINV").evaluate(option_snapshot())[0]
        self.assertEqual((row["legs"][0]["put_call"],row["legs"][0]["side"]),("PUT","BUY"))

    def test_vertical_becomes_opposite_debit_vertical(self):
        row=OptionInverse(lambda:_OptionOriginal(True),"VERTINV").evaluate(option_snapshot())[0]
        self.assertEqual([(x["strike"],x["side"]) for x in row["legs"]],[(100.0,"SELL"),(102.0,"BUY")])
        debit=row["legs"][1]["ask"]-row["legs"][0]["bid"]
        self.assertGreater(debit,0)


if __name__ == "__main__": unittest.main()
