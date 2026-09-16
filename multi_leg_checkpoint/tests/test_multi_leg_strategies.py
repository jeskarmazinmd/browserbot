import inspect
import unittest
from datetime import datetime, timedelta, timezone

from engine.events import MarketSnapshot, Quote
from strategies.strategy_pairmr1 import PAIRMR1Strategy
from strategies.strategy_leadbask1 import LEADBASK1Strategy
from strategies.strategy_sectorh1 import SECTORH1Strategy
import strategies.strategy_pairmr1 as pairmr1
import strategies.strategy_leadbask1 as leadbask1
import strategies.strategy_sectorh1 as sectorh1


MODULES = (pairmr1, leadbask1, sectorh1)


def snap(when, prices):
    return MarketSnapshot(
        timestamp=when,
        quotes={s: Quote(price=float(p), total_volume=1_000_000) for s, p in prices.items()},
        expected_symbol_count=len(prices),
        returned_symbol_count=len(prices),
        fetch_duration_seconds=0.01,
    )


class MultiLegStrategyTests(unittest.TestCase):
    def test_all_are_prospective_paper_only_and_self_contained(self):
        forbidden = (
            "xs_adaptive", "xs_executor", "derived_runtime", "snapshot_common",
            "strategy_td1", "strategy_q", "strategy_p", "strategy_gt1",
        )
        for module in MODULES:
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            self.assertEqual(module.FORWARD_START_UTC, "2026-08-10T13:30:00+00:00")
            source = inspect.getsource(module)
            for token in forbidden:
                self.assertNotIn(token, source)

    def test_forward_gate_blocks_prebirth_signals(self):
        when = datetime(2026, 8, 10, 13, 29, tzinfo=timezone.utc)
        prices = {s: 100 for s in set(pairmr1.CANDIDATES) | set(leadbask1.CANDIDATES) | set(sectorh1.STOCKS) | {sectorh1.HEDGE}}
        for strategy in (PAIRMR1Strategy(), LEADBASK1Strategy(), SECTORH1Strategy()):
            self.assertEqual(strategy.on_snapshot(snap(when, prices)), [])

    def test_sector_hedge_emits_coordinated_opposite_legs(self):
        strategy = SECTORH1Strategy()
        start = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
        for i in range(31):
            prices = {sectorh1.HEDGE: 100.0 + i*0.01}
            prices.update({s: 100.0 for s in sectorh1.STOCKS})
            prices["NVDA"] = 100.0 + i*0.08
            out = strategy.on_snapshot(snap(start+timedelta(minutes=i), prices))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].signal_type, "MULTI_LEG")
        legs = out[0].data["legs"]
        self.assertEqual(len(legs), 2)
        self.assertEqual(legs[0]["symbol"], "NVDA")
        self.assertEqual(legs[0]["side"], "LONG")
        self.assertEqual(legs[1]["symbol"], "QQQ")
        self.assertEqual(legs[1]["side"], "SHORT")


if __name__ == "__main__":
    unittest.main()
