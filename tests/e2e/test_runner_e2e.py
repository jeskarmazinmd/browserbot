from __future__ import annotations
import importlib, json, math, os, shutil, sys, tempfile, unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Permit importing the runner in a local test environment without Schwab SDK setup.
if "schwab_clients" not in sys.modules:
    stub = ModuleType("schwab_clients")
    class SchwabTradeClient: pass
    stub.SchwabTradeClient = SchwabTradeClient
    sys.modules["schwab_clients"] = stub

ACC = ROOT / "tests" / "acceptance"
SPECS = json.loads((ACC / "scanner_fixture_specs.json").read_text())
EXPLICIT = {
    "TL1": np.r_[np.linspace(100,103,29),102.4,103.3],
    "HL1": np.array([100,99.8,99.5,99.2,98.8,98.0,99.0,99.5,100,99.7,99.0,98.5,99.2,99.6,100,100.2,100.4,100.5,100.6,100.7,100.9]),
    "EMA1": np.loadtxt(ACC / "EMA1.txt"),
    "SMA1": np.loadtxt(ACC / "SMA1.txt"),
    "VT1": np.loadtxt(ACC / "VT1.txt"),
}

def pattern(name):
    if name=='opening': return np.r_[np.linspace(100,100.5,15),np.full(5,100.4),100.8]
    kind,n=name.rsplit('_',1); n=int(n)
    if kind=='up': return np.linspace(100,104,n)
    if kind=='down': return np.linspace(104,100,n)
    if kind=='flatbreak': return np.r_[np.full(n-1,100.0),100.3]
    if kind=='upbreak': return np.r_[np.linspace(100,103,n-1),103.5]
    if kind=='downrebound': return np.r_[np.linspace(104,99,n-4),98.8,99.0,99.2,99.5]
    if kind=='v': return np.r_[np.linspace(102,98,n//2),np.linspace(98,101,n-n//2)]
    if kind=='pullback': return np.r_[np.linspace(100,104,n-5),104,103.7,103.6,103.7,103.9]
    if kind=='reclaim': return np.r_[np.full(n-5,100),98.5,99.0,99.8,100.2,100.3]
    if kind=='flatten': return np.r_[np.linspace(104,100,n//2),np.linspace(100,99.7,n-n//2-4),99.65,99.7,99.8,99.9]
    raise KeyError(name)

class OneFrameSource:
    def __init__(self, frame):
        self.frame = frame
        self.finished = True
        self._now = frame["timestamp"].max()
    def read_data(self): return self.frame
    def now(self): return self._now

class MultiFrameSource:
    def __init__(self, frames):
        self.frames = frames; self.i = -1
    def read_data(self):
        self.i = min(self.i + 1, len(self.frames)-1)
        return self.frames[self.i]
    def now(self): return self.frames[max(self.i,0)]["timestamp"].max()
    @property
    def finished(self): return self.i >= len(self.frames)-1


def import_runner(run_id):
    os.environ["RUN_MODE"] = "REPLAY"
    os.environ["RUN_ID"] = run_id
    os.environ["REPLAY_TAPE_PATH"] = "unused.csv"
    for name in ["bot_output", "live_strategy_runner"]:
        sys.modules.pop(name, None)
    return importlib.import_module("live_strategy_runner")


def read_events(root):
    path = root / "bot_events.jsonl"
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

class RunnerEndToEndTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("RUN_MODE", None); os.environ.pop("RUN_ID", None); os.environ.pop("REPLAY_TAPE_PATH", None)

    def test_01_actual_runner_logs_all_25_independent_scanners(self):
        runner = import_runner("e2e_all_scanners")
        modules = runner.evaluate_registered_strategies.__globals__["ENABLED_STRATEGIES"]
        start=pd.Timestamp("2026-08-03T14:00:00Z")
        rows=[]; symbol_to_sid={}
        for idx,module in enumerate(modules):
            symbol=f"T{idx:02d}"; symbol_to_sid[symbol]=module.STRATEGY_ID
            for ts,px in zip(pd.date_range(start,periods=20,freq="min",tz="UTC"),np.linspace(100,101,20)):
                rows.append((ts,symbol,float(px)))
        frame=pd.DataFrame(rows,columns=["timestamp","symbol","price"])
        runner.quote_source=OneFrameSource(frame)
        runner.load_positions=lambda: {}
        runner.detect_latest_flash=lambda *a,**k: None
        runner.minute_prices=lambda g: pd.Series(dtype=float)
        def injected(sym,g,spy=None):
            sid=symbol_to_sid[sym]
            ts=g["timestamp"].max()
            return [{"strategy_id":sid,"symbol":sym,"timestamp":pd.Timestamp(ts).isoformat(),"entry_price":float(g["price"].iloc[-1]),"target_price":102.0,"stop_price":99.0,"setup_id":f"{sid}|{sym}|x","live_order_placement":False}]
        runner.detect_independent_signals=injected
        outroot=runner.DATA_ROOT
        shutil.rmtree(outroot,ignore_errors=True); outroot.mkdir(parents=True,exist_ok=True)
        runner.main()
        events=read_events(outroot)
        got={e.get("strategy_id") for e in events if e.get("event_type")=="SIGNAL"}
        expected={m.STRATEGY_ID for m in modules}
        self.assertEqual(expected,got, f"missing={sorted(expected-got)} extra={sorted(got-expected)}")
        self.assertTrue((outroot/"bot_history.jsonl").exists())

    def test_02_actual_flash_orchestration_logs_pending_confirmed_and_signal(self):
        runner=import_runner("e2e_flash_signal")
        start=pd.Timestamp("2026-08-03T14:00:00Z")
        f1=pd.DataFrame({"timestamp":[start],"symbol":["FLASH"],"price":[100.0]})
        f2=pd.DataFrame({"timestamp":[start,start+pd.Timedelta(minutes=1)],"symbol":["FLASH","FLASH"],"price":[100.0,100.25]})
        runner.quote_source=MultiFrameSource([f1,f2])
        runner.load_positions=lambda: {}
        runner.detect_independent_signals=lambda *a,**k: []
        event={"symbol":"FLASH","flash_drop_pct":1.5,"flash_start_price":101.5,"target_price":100.9,"pre_return_pct":1.0,"pre_slope_pct_per_hour":2.0,"pre_r2":.9,"signal_window_end":start.isoformat(),"entry_price":100.0}
        calls={"n":0}
        def detector(*a,**k):
            calls["n"]+=1
            return dict(event) if calls["n"]==1 else None
        runner.detect_latest_flash=detector
        runner.fetch_flash_volume_metrics=lambda sym: {"flash_dollar_volume_3m":250000.0}
        runner.fetch_rebound_volume_metrics=lambda *a,**k: {}
        outroot=runner.DATA_ROOT; shutil.rmtree(outroot,ignore_errors=True); outroot.mkdir(parents=True,exist_ok=True)
        runner.main()
        events=read_events(outroot); types=[e.get("event_type") for e in events]
        self.assertIn("PENDING_REBOUND_CREATED",types)
        self.assertIn("REBOUND_CONFIRMED",types)
        self.assertIn("SIGNAL",types)
        signal_ids={e.get("strategy_id") for e in events if e.get("event_type")=="SIGNAL"}
        self.assertTrue({"A","B","D"}.issubset(signal_ids),signal_ids)

    def test_03_actual_runner_logs_threshold_near_miss_and_dashboard_row(self):
        runner=import_runner("e2e_flash_near_miss")
        start=pd.Timestamp("2026-08-03T14:00:00Z")
        frame=pd.DataFrame({"timestamp":[start],"symbol":["NEAR"],"price":[100.64]})
        runner.quote_source=OneFrameSource(frame)
        runner.load_positions=lambda: {}
        runner.detect_independent_signals=lambda *a,**k: []
        runner.detect_latest_flash=lambda *a,**k: None
        # 34 continuous prices: strong pretrend and 0.85% flash drop.
        vals=np.r_[np.linspace(100,101.5,31),101.30,101.0,100.63725]
        idx=pd.date_range(start-pd.Timedelta(minutes=len(vals)-1),periods=len(vals),freq="min",tz="UTC")
        runner.minute_prices=lambda g: pd.Series(vals,index=idx)
        outroot=runner.DATA_ROOT; shutil.rmtree(outroot,ignore_errors=True); outroot.mkdir(parents=True,exist_ok=True)
        runner.main()
        events=read_events(outroot)
        near=[e for e in events if e.get("event_type")=="NEAR_MISS"]
        self.assertTrue(near,"runner emitted no NEAR_MISS event")
        self.assertTrue({e.get("strategy_id") for e in near} & {"A","B","D","H"})
        history=[json.loads(x) for x in (outroot/"bot_history.jsonl").read_text().splitlines() if x.strip()]
        self.assertEqual("no_trigger",history[-1]["status"])
        self.assertTrue(history[-1]["latest_nearest"])

if __name__=="__main__": unittest.main(verbosity=2)
