import multiprocessing as mp
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import system_load_test as load


class SystemLoadTestTests(unittest.TestCase):
    def test_generates_full_synthetic_universe(self):
        rows=load.synthetic_payloads(2700,3)
        self.assertEqual(len(rows),2700)
        self.assertTrue({"SPY","QQQ","IWM"} <= set(rows))

    def test_source_has_no_network_or_execution_client(self):
        source=Path("system_load_test.py").read_text()
        self.assertNotIn("import requests",source)
        self.assertNotIn("get_schwab_client",source)
        self.assertNotIn("SchwabTradeClient",source)
        self.assertNotIn('Path("/data")',source)

    def test_safety_aborts_on_tiny_memory_requirement(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(load, "mem_available_mb", return_value=512):
                with self.assertRaises(load.AbortTest):
                    load.safety(Path(root), 1024, 256, 100)

    def test_family_emulator_finishes(self):
        queue=mp.Queue()
        process=mp.Process(target=load.family_child,args=("crosssection",1,.03,100,queue))
        process.start();process.join(2)
        self.assertFalse(process.is_alive())
        self.assertEqual(queue.get(timeout=1)["family"],"crosssection")


if __name__=="__main__":unittest.main()
