from __future__ import annotations
import json, math, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from strategies.manifest import STRATEGY_MANIFEST, STRATEGY_MODULES
from strategies.registry import (
    ENABLED_STRATEGIES, FLASH_STRATEGY_MODULES, REPORTING_STRATEGY_MODULES,
    evaluate_all,
)


def simple_return_pct(a, b):
    a=float(a); b=float(b)
    return (b/a-1.0)*100.0 if a else math.nan

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def fit_log_slope_pct_per_hour(series):
    values=np.asarray(series,dtype=float)
    if len(values)<2 or np.any(values<=0): return math.nan, math.nan
    x=np.arange(len(values),dtype=float); y=np.log(values)
    slope,intercept=np.polyfit(x,y,1); pred=intercept+slope*x
    ss_res=float(np.sum((y-pred)**2)); ss_tot=float(np.sum((y-y.mean())**2))
    r2=1.0-ss_res/ss_tot if ss_tot>0 else 1.0
    return (math.exp(float(slope)*60.0)-1.0)*100.0, r2

def signal_factory(strategy_id, symbol, timestamp, entry_price, target_pct, stop_pct, reason, **metrics):
    return {
        'strategy_id': strategy_id, 'symbol': symbol, 'timestamp': str(timestamp),
        'entry_price': float(entry_price), 'target_pct': float(target_pct),
        'stop_pct': float(stop_pct), 'reason': reason, **metrics,
    }

def volume_ratio(*args, **kwargs):
    return 2.0

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

def context(prices, *, minute_et=600, ret=2.0, slope=4.0, r2=.95, spy=0.0, start='2026-08-03T13:30:00Z'):
    prices=pd.Series(np.asarray(prices,dtype=float))
    timestamps=pd.date_range(start,periods=len(prices),freq='min',tz='UTC')
    work=pd.DataFrame({'timestamp':timestamps,'price':prices,'volume':np.linspace(100,300,len(prices))})
    return SimpleNamespace(
        symbol='TEST', work=work, timestamp=timestamps[-1], current_price=float(prices.iloc[-1]),
        minute_et=minute_et, prices=prices, return_30m_pct=ret,
        slope_30m_pct_per_hour=slope, r2_30m=r2, spy_30m_return_pct=spy,
        signal_factory=signal_factory, simple_return_pct=simple_return_pct,
        fit_log_slope_pct_per_hour=fit_log_slope_pct_per_hour, ema=ema,
        confirm_recent_volume_ratio=volume_ratio,
    )

FIXTURE_SPECS=json.loads((Path(__file__).with_name('scanner_fixture_specs.json')).read_text())
EXPLICIT={
    'TL1': np.r_[np.linspace(100,103,29),102.4,103.3],
    'HL1': np.array([100,99.8,99.5,99.2,98.8,98.0,99.0,99.5,100,99.7,99.0,98.5,99.2,99.6,100,100.2,100.4,100.5,100.6,100.7,100.9]),
    'EMA1': np.loadtxt(Path(__file__).with_name('EMA1.txt')),
    'SMA1': np.loadtxt(Path(__file__).with_name('SMA1.txt')),
    'VT1': np.loadtxt(Path(__file__).with_name('VT1.txt')),
}

class AcceptanceTests(unittest.TestCase):
    def test_01_manifest_has_exactly_60_unique_modules(self):
        self.assertEqual(60,len(STRATEGY_MANIFEST))
        self.assertEqual(60,len(set(STRATEGY_MANIFEST)))

    def test_02_expected_architecture_split(self):
        self.assertEqual(4,len(FLASH_STRATEGY_MODULES))
        self.assertEqual(25,len(ENABLED_STRATEGIES))
        self.assertEqual(31,len(REPORTING_STRATEGY_MODULES))
        self.assertEqual(60,4+25+31)

    def test_03_all_derived_variants_have_metadata_and_config(self):
        for sid,module in REPORTING_STRATEGY_MODULES.items():
            with self.subTest(strategy=sid):
                raw=module.metadata()
                self.assertEqual(sid,raw['strategy_id'])
                self.assertTrue(raw.get('description'))
                self.assertIsInstance(raw.get('config'),dict)

    def test_04_flash_strategies_positive_boundary_entry_and_near_miss(self):
        for sid,module in FLASH_STRATEGY_MODULES.items():
            cfg=module.CONFIG
            base={'flash_drop_pct':cfg['flash_drop_pct'],'target_price':101.0,'pre_r2':.9,'pre_slope_pct_per_hour':2.0}
            with self.subTest(strategy=sid,state='signal'):
                self.assertTrue(module.accepts_flash(base,12.0))
                refreshed=module.refresh_event_for_entry(base,100.0)
                ok,reason=module.validate_confirmed_entry(refreshed,0.10)
                self.assertTrue(ok,reason)
                self.assertEqual(sid,refreshed['strategy_id'])
                self.assertAlmostEqual(100*(1-cfg['stop_loss_fraction']),refreshed['stop_price'])
            with self.subTest(strategy=sid,state='near_miss_below_drop'):
                near=dict(base,flash_drop_pct=cfg['flash_drop_pct']-0.01)
                self.assertFalse(module.accepts_flash(near,12.0))
            with self.subTest(strategy=sid,state='invalid_entry'):
                bad=module.refresh_event_for_entry(base,101.0)
                ok,reason=module.validate_confirmed_entry(bad,0.10)
                self.assertFalse(ok)
                self.assertIn(reason,{'target_reached_before_entry','insufficient_remaining_upside'})

    def test_05_every_independent_scanner_generates_expected_signal(self):
        for module in ENABLED_STRATEGIES:
            sid=module.STRATEGY_ID
            with self.subTest(strategy=sid):
                if sid in EXPLICIT:
                    prices=EXPLICIT[sid]; spec={'ret':2,'slope':4,'r2':.95,'spy':0}
                else:
                    spec=FIXTURE_SPECS[sid]; prices=pattern(spec['pattern'])
                minute=590 if sid=='OR1' else 600
                out=module.evaluate(context(prices,minute_et=minute,ret=spec['ret'],slope=spec['slope'],r2=spec['r2'],spy=spec['spy']))
                self.assertGreaterEqual(len(out),1)
                self.assertEqual(sid,out[0]['strategy_id'])
                self.assertEqual('TEST',out[0]['symbol'])

    def test_06_every_independent_scanner_handles_clear_negative_without_error(self):
        flat=np.full(90,100.0)
        for module in ENABLED_STRATEGIES:
            with self.subTest(strategy=module.STRATEGY_ID):
                out=module.evaluate(context(flat,ret=0,slope=0,r2=0,spy=0,minute_et=700))
                self.assertIsInstance(out,list)

    def test_07_registry_isolates_one_broken_strategy(self):
        good=SimpleNamespace(STRATEGY_ID='GOOD',evaluate=lambda ctx:[{'strategy_id':'GOOD'}])
        def fail(ctx): raise RuntimeError('intentional')
        bad=SimpleNamespace(STRATEGY_ID='BAD',evaluate=fail)
        import strategies.registry as registry
        original=registry.ENABLED_STRATEGIES
        try:
            registry.ENABLED_STRATEGIES=[bad,good]
            signals,errors=registry.evaluate_all(object())
        finally:
            registry.ENABLED_STRATEGIES=original
        self.assertEqual([{'strategy_id':'GOOD'}],signals)
        self.assertEqual('BAD',errors[0][0])

    def test_08_bot_output_replay_logging(self):
        old_mode=os.environ.get('RUN_MODE'); old_id=os.environ.get('RUN_ID')
        os.environ['RUN_MODE']='REPLAY'; os.environ['RUN_ID']='acceptance_logging'
        try:
            if 'bot_output' in sys.modules: del sys.modules['bot_output']
            import bot_output
            if bot_output.OUTPUT_ROOT.exists():
                import shutil; shutil.rmtree(bot_output.OUTPUT_ROOT)
            bot_output.write_bot_output(status='acceptance',triggers=[{'strategy_id':'A'}],nearest=[{'strategy_id':'A','miss_score':0.1}])
            bot_output.append_bot_event('ACCEPTANCE_EVENT',strategy_id='A')
            self.assertTrue(bot_output.HISTORY_JSONL.exists())
            self.assertTrue(bot_output.EVENTS_JSONL.exists())
            history=json.loads(bot_output.HISTORY_JSONL.read_text().splitlines()[-1])
            event=json.loads(bot_output.EVENTS_JSONL.read_text().splitlines()[-1])
            self.assertEqual('acceptance',history['status'])
            self.assertEqual('ACCEPTANCE_EVENT',event['event_type'])
        finally:
            if old_mode is None: os.environ.pop('RUN_MODE',None)
            else: os.environ['RUN_MODE']=old_mode
            if old_id is None: os.environ.pop('RUN_ID',None)
            else: os.environ['RUN_ID']=old_id

if __name__=='__main__': unittest.main(verbosity=2)
