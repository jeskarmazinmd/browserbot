import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import xs_shadow_worker as worker
from research_lab.xs_executor import XSSharedRuntime
from research_lab.xs_shadows import ready_shadow_specs


class XSShadowWorkerTests(unittest.TestCase):
    def test_incomplete_and_premarket_minutes_are_excluded(self):
        frame=pd.DataFrame({
            "timestamp":[
                "2026-08-10T13:29:00Z",
                "2026-08-10T13:30:00Z",
                "2026-08-10T13:31:00Z",
            ],
            "symbol":["X","X","X"],
            "price":[99,100,101],
        })
        wide=worker.complete_regular_prices(frame,"2026-08-10T13:31:30Z")
        self.assertEqual(list(wide.index),[pd.Timestamp("2026-08-10T13:30:00Z")])

    def test_manifest_preserves_original_birth_for_same_specification(self):
        specs=ready_shadow_specs()[:1]
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"manifest.json"
            first=worker.ensure_manifest(path,specs,"2026-08-08T10:00:00Z")
            second=worker.ensure_manifest(path,specs,"2026-08-09T10:00:00Z")
            name=specs[0].name
            self.assertEqual(first[name]["experiment_id"],second[name]["experiment_id"])
            self.assertEqual(first[name]["born_at"],second[name]["born_at"])
            self.assertEqual(len(json.loads(path.read_text())),1)

    def test_cache_signature_changes_only_when_cache_revision_changes(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"minute.pkl"
            path.write_bytes(b"one")
            first=worker.cache_signature(path)
            self.assertEqual(first,worker.cache_signature(path))
            path.write_bytes(b"a different revision")
            self.assertNotEqual(first,worker.cache_signature(path))

    def test_frozen_prediction_contains_no_realized_outcome(self):
        times=pd.date_range("2026-08-10T13:30:00Z",periods=40,freq="min")
        rng=np.random.default_rng(8)
        a=rng.normal(0,.003,len(times))
        b=np.zeros(len(times))
        b[1:]=a[:-1]
        # Keep the learned relationship unchanged while making the current
        # prospective long signal unambiguously positive.
        a[-1]=.01
        returns=pd.DataFrame({"A":a,"B":b},index=times)
        wide=100*(1+returns).cumprod()
        spec=next(x for x in ready_shadow_specs() if x.name=="LL30H1K1")
        runtime=XSSharedRuntime((spec,))
        predictions=runtime.update(wide)
        with tempfile.TemporaryDirectory() as root:
            manifest=worker.ensure_manifest(
                Path(root)/"manifest.json",(spec,),"2026-08-10T13:30:00Z"
            )
            rows=[]
            worker.freeze_predictions(predictions,wide,manifest,rows.append)
        self.assertTrue(rows)
        self.assertTrue(all("realized_return" not in row for row in rows))
        self.assertTrue(all(row["side"]=="LONG" for row in rows))


if __name__=="__main__":
    unittest.main()
