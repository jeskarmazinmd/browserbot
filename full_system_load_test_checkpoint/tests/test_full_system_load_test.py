import unittest
from pathlib import Path
import full_system_load_test as full

class FullSystemLoadTests(unittest.TestCase):
    def test_all_runtime_families_are_named(self):
        self.assertEqual(len(full.FAMILIES),13)
        self.assertTrue({"collector","main","xs","options","options_rv","futures_curve","swing"}<=set(full.FAMILIES))
    def test_synthetic_inputs_have_expected_shapes(self):
        now=full.datetime(2026,8,10,14,tzinfo=full.timezone.utc)
        self.assertEqual(len(full.equity_quotes(full.symbols(2700),0,now)),2700)
        self.assertGreaterEqual(len(full.option_contracts("SPY",0)),100)
        self.assertEqual(set(full.futures_roots(0,now)),{"/MES","/MNQ","/MGC","/MCL","/M6E"})
        self.assertTrue(all(len(x)==3 for x in full.curves(0,now).values()))
    def test_guards_reject_network_and_data_writes(self):
        with self.assertRaises(PermissionError):full.deny_external("socket.connect",("x",))
        with self.assertRaises(PermissionError):full.deny_external("open",("/data/test.json","w"))
        full.deny_external("open",("/tmp/test.json","w"))
    def test_harness_contains_no_network_client(self):
        source=Path("full_system_load_test.py").read_text()
        self.assertNotIn("import requests",source)
        self.assertNotIn("get_schwab_client",source)
        self.assertNotIn("SchwabTradeClient",source)
    def test_snapshot_prewarm_collapses_history_to_terminal_state(self):
        self.assertEqual(list(full.warm_steps(75,"snapshot")),[74])
        self.assertEqual(list(full.warm_steps(0,"snapshot")),[])
        self.assertEqual(list(full.warm_steps(3,"replay")),[0,1,2])

if __name__=="__main__":unittest.main()
