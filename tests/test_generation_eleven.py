"""Synthetic execution-contract tests, not historical trades or backtests."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from engine.events import MarketSnapshot, Quote
from strategies import generation_eleven as g
from strategies import generation_eleven_retirement as retirement
from strategies.output_switches import output_enabled
from generation_eleven_paper_tracker import GenerationElevenTracker, FILE_STEM, fee
from reporting.generation_eleven_performance import calculate_generation_eleven

NOW=datetime(2026,10,21,17,30,tzinfo=timezone.utc)
BIRTH=NOW-timedelta(hours=4)


def activation(root):
    r=dict(schema='G11_ACTIVATION_V1',population_hash=g.POPULATION_HASH,
           evidence_manifest_sha256=retirement.plan()['evidence_manifest_sha256'],
           parents=retirement.plan()['parents'],retired_count=722,historical_prefixes_verified=True,verified_prefixes={})
    (Path(root)/'g11_activation.json').write_text(json.dumps(r))
    return r


def quote(now=NOW, bid=19.999, ask=20.,size=10000):
    return dict(bid=bid,ask=ask,bid_time_ms=now.timestamp()*1000,ask_time_ms=now.timestamp()*1000,
                bid_size_raw=size,ask_size_raw=size,realtime=True)


def signal(sid,now=NOW):
    s=g.SPECS[sid]
    e=dict(strategy_id=sid,timestamp=now.isoformat(),symbol='XYZ',entry_price=20.,
           paper_only=True,live_order_placement=False,rule_version=g.RULE_VERSION,
           population_hash=g.POPULATION_HASH,config_hash=g.metadata(sid)['config_hash'])
    if s.mode=='FLASH':
        e.update(flash_drop_pct=3.,original_flash_drop_pct=3.,pre_return_pct=3.,pre_r2=.95,
                 original_target_price=22.4,target_price=22.4,flash_start_price=24.,running_low_price=19.6,
                 pending_created_at=(now-timedelta(seconds=180)).isoformat(),actual_rebound_pct=(20/19.6-1)*100,
                 confirmation_wait_seconds=180)
    else:
        e.update(source_parent=s.parent,parent_votes=[p for p in (s.parent,s.secondary) if p],
                 completed_minute=now.replace(second=0,microsecond=0).isoformat(),
                 g11_market5=1.,g11_symbol_vol=.05)
    return e


class G11Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        activation(self.root)
        self.env=patch.dict(os.environ,ENABLE_G11_PAPER='1',G11_ACTIVATION_PATH=str(self.root/'g11_activation.json'),
                            ENABLE_G9_RETIREMENTS='0',ENABLE_G8_RETIREMENTS='0')
        self.env.start();retirement._activation.cache_clear()
        self.t=GenerationElevenTracker(self.root,now_provider=lambda:BIRTH)
    def tearDown(self):
        self.t.close();self.env.stop();retirement._activation.cache_clear();self.temp.cleanup()
    def test_population_and_retirement(self):
        self.assertEqual(len(g.IDS),722)
        self.assertEqual(Counter(s.family for s in g.CATALOG),g.FAMILY_COUNTS)
        self.assertEqual(len({g.digest({k:v for k,v in g.metadata(s.strategy_id)['parameters'].items() if k not in {'strategy_id','family','hypothesis'}}) for s in g.CATALOG}),722)
        self.assertEqual(sum(output_enabled(s) for s in retirement.plan()['parents']),12)
        self.assertFalse(any(output_enabled(s) for s in retirement.plan()['retired_report_ids']))
        self.assertTrue(all(output_enabled(s) for s in g.IDS))
        self.assertFalse(output_enabled('UNREVIEWED_PAPER_OUTPUT'))
        self.assertEqual(len(retirement.kept()|g.IDS),734)
    def test_every_candidate_can_open_and_close_independently(self):
        self.t.observe_minute(NOW,g.MINUTE_IDS,NOW);self.t.observe_scan(NOW,100)
        self.t.update_quotes({},NOW)
        for s in g.CATALOG:
            with self.subTest(sid=s.strategy_id):
                self.assertTrue(self.t.register_signal(signal(s.strategy_id),quote(),NOW),self.t.reasons)
        self.assertEqual(len(self.t.active),722)
        self.assertEqual(len({r['setup_id'] for r in self.t.active.values()}),722)
        later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=24.,ask=24.001)},later)
        self.assertFalse(self.t.active)
        self.assertEqual(sum(self.t.completed.values()),722)
        self.assertTrue(all(v==1 for v in self.t.completed.values()))
        self.assertTrue(all(self.t.cash[sid]>5000 for sid in g.IDS))
    def test_restart_retains_cash_births_seen_and_exits(self):
        sid='G11ENTRY001';self.t.observe_minute(NOW,g.MINUTE_IDS,NOW)
        self.assertTrue(self.t.register_signal(signal(sid),quote(),NOW))
        births=self.t.births.copy();cash=self.t.cash[sid]
        self.t.close();self.t=GenerationElevenTracker(self.root,now_provider=lambda:NOW)
        self.assertEqual(self.t.births,births);self.assertEqual(self.t.cash[sid],cash)
        self.assertFalse(self.t.register_signal(signal(sid),quote(),NOW))
        later=NOW+timedelta(minutes=1);self.t.update_quotes({'XYZ':quote(later,bid=25.,ask=25.001)},later)
        self.assertEqual(self.t.completed[sid],1)
        self.assertFalse(any(output_enabled(s) for s in retirement.plan()['retired_report_ids']))
    def test_stale_quotes_no_whole_share_and_paper_contract(self):
        sid='G11ENTRY001'
        self.assertFalse(self.t.register_signal(signal(sid),quote(NOW-timedelta(seconds=10)),NOW))
        later=NOW+timedelta(minutes=1)
        self.assertFalse(self.t.register_signal(signal(sid,later),quote(later,bid=1999.,ask=2000.),later))
        later+=timedelta(minutes=1);e=signal(sid,later);e['live_order_placement']=True
        self.assertFalse(self.t.register_signal(e,quote(later),later))
        self.assertEqual(self.t.cash[sid],5000.)
    def test_partial_exit_and_pending_reason_survive_restart(self):
        sid='G11ENTRY001';self.assertTrue(self.t.register_signal(signal(sid),quote(),NOW))
        later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=25.,ask=25.001,size=1)},later)
        self.assertTrue(self.t.active)
        self.t.close();self.t=GenerationElevenTracker(self.root,now_provider=lambda:later)
        self.assertTrue(next(iter(self.t.active.values()))['pending_exit_reason'])
        later+=timedelta(minutes=1);self.t.update_quotes({'XYZ':quote(later,bid=24.,ask=24.001)},later)
        self.assertEqual(self.t.completed[sid],1)
    def test_day_start_costs_and_distinct_pnl_fields(self):
        sid='G11ENTRY001';self.t.observe_minute(NOW,g.MINUTE_IDS,NOW)
        self.assertTrue(self.t.register_signal(signal(sid),quote(),NOW))
        row=next(iter(self.t.active.values()));qty=row['filled_qty']
        self.t.snapshot({'XYZ':quote()},NOW)
        a=self.t.snapshots[sid]
        self.assertAlmostEqual(a['realized_pnl'],-fee(qty))
        self.assertLess(a['unrealized_hypothetical_close_pnl'],0)
        self.assertAlmostEqual(a['daily_pnl'],a['realized_pnl']+a['unrealized_hypothetical_close_pnl'])
        self.t.snapshot({},NOW)
        self.assertIsNone(self.t.snapshots[sid]['unrealized_hypothetical_close_pnl'])
        self.assertIsNone(self.t.snapshots[sid]['equity'])
    def test_report_recognizes_all_births_without_inventing_returns(self):
        modules,diag=calculate_generation_eleven(self.root,'2026-10-21',NOW)
        self.assertEqual(len(modules),722)
        self.assertTrue(all(r['return_pct'] is None for r in modules.values()))
        self.t.observe_minute(NOW,g.MINUTE_IDS,NOW);self.t.observe_scan(NOW,100);self.t.update_quotes({},NOW)
        modules,diag=calculate_generation_eleven(self.root,'2026-10-21',NOW)
        self.assertEqual(len(modules),722)
        self.assertTrue(all(r['return_pct']==0 for r in modules.values()))
    def test_minute_hub_executes_owned_evaluators_and_emits_provenance(self):
        hub=g.MinuteHub();events=[]
        for i in range(100):
            t=NOW.replace(hour=13,minute=30)+timedelta(minutes=i)
            prices={s:Quote(20*(1+.001*i)) for s in set(g3_universe())}
            prices['SPY']=Quote(100*(1+.00001*i))
            snap=MarketSnapshot(t,prices,len(prices),len(prices),.1)
            events.extend(e for e in hub.on_snapshot(snap) if e.signal_type!='G11_OBSERVATION')
        self.assertTrue(events)
        self.assertTrue(all(e.strategy_id in g.MINUTE_IDS for e in events))
        self.assertTrue(all(e.data['config_hash']==g.metadata(e.strategy_id)['config_hash'] for e in events))
        self.assertTrue(any(g.SPECS[e.strategy_id].secondary for e in events))
        self.assertEqual(hub.on_snapshot(snap),[])
    def test_no_existing_ledger_overwritten_or_orphan_reinitialized(self):
        legacy=self.root/'paper_generation_nine_sthedge2_outcomes.jsonl';legacy.write_text('sentinel\n')
        before=legacy.read_bytes();self.t.close()
        (self.root/(FILE_STEM+'_births.json')).unlink()
        with self.assertRaisesRegex(ValueError,'births missing'):
            GenerationElevenTracker(self.root,now_provider=lambda:NOW)
        self.assertEqual(legacy.read_bytes(),before)
    def test_parent_sources_unchanged_and_g9_sizing_preserved(self):
        root=Path(__file__).resolve().parents[1]
        m=json.loads((root/'research_tools/g11/PRESERVATION_MANIFEST.json').read_text())
        for name in ['strategies/generation_three.py','strategies/generation_six.py','strategies/generation_seven.py',
                     'strategies/generation_nine.py','generation_nine_paper_tracker.py','generation_ten_paper_tracker.py']:
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),m['source_files'][name]['sha256'])
    def test_broker_path_has_explicit_g11_guard(self):
        source=(Path(__file__).resolve().parents[1]/'live_strategy_runner.py').read_text()
        self.assertIn("startswith(('G10', 'G11')):\n                        continue",source)
    def test_rollback_restores_previous_output_controls(self):
        with patch.dict(os.environ,ENABLE_G11_PAPER='0'):
            self.assertTrue(output_enabled('G10ENTRY01'))
    def test_readiness_requires_covered_completed_market_inputs(self):
        self.t.observe_minute(NOW,[],NOW)
        self.assertFalse(self.t.observed)
        self.t.observe_minute(NOW,g.MINUTE_IDS,NOW-timedelta(minutes=3))
        self.assertFalse(self.t.observed)
        hub=g.MinuteHub()
        snap=MarketSnapshot(NOW,{'SPY':Quote(100.)},1,1,.1)
        observation=hub.on_snapshot(snap)[0]
        self.assertEqual(observation.signal_type,'G11_OBSERVATION')
        self.assertEqual(observation.data['ready_ids'],[])
    def test_family_rules_change_admission_and_actual_position_size(self):
        early=NOW.replace(hour=13,minute=31)
        e=signal('G11ENTRY001',early)
        self.assertEqual(g.admission(g.SPECS['G11ENTRY001'],e,20.,19.999,early),'time_window')
        for sid in ['G11RISK001','G11RISK010']:
            self.assertTrue(self.t.register_signal(signal(sid),quote(),NOW))
        quantities={r['strategy_id']:r['filled_qty'] for r in self.t.active.values()}
        self.assertNotEqual(quantities['G11RISK001'],quantities['G11RISK010'])
        sid='G11REGIME001';e=signal(sid);e['g11_market5']=-1.
        self.assertFalse(self.t.register_signal(e,quote(),NOW))
        sid='G11COMBO001';e=signal(sid);e['parent_votes']=[g.SPECS[sid].parent]
        self.assertFalse(self.t.register_signal(e,quote(),NOW))
    def test_enabled_registry_has_executable_hub_and_flash_candidates(self):
        code='''
from strategies import registry, generation_eleven as g
assert not registry.FAILED_STRATEGIES, registry.FAILED_STRATEGIES
assert g.FLASH_IDS <= set(registry.flash_strategy_configs())
assert sum(s.name=='G11HUB' for s in registry.MINUTE_STRATEGIES)==1
from strategies.manifest import load_modules
assert g.IDS <= set(load_modules())
'''
        subprocess.run([sys.executable,'-c',code],env=os.environ.copy(),check=True,capture_output=True)
    def test_production_verifier_distinguishes_births_from_observed_outcomes(self):
        from research_tools.g11.verify_production import inspect
        expected=set(retirement.plan()['parents'])|{sid+'BA' for sid in g.IDS}
        (self.root/'all_engine_performance_live.json').write_text(json.dumps(dict(modules={sid:{} for sid in expected})))
        warm=inspect(self.root,allow_warmup=True)
        self.assertFalse(warm['errors'])
        self.assertEqual((warm['g11_active'],warm['preserved_active'],warm['original_retired']),(722,12,722))
        self.assertEqual(warm['recorded_opens'],0)
        self.assertTrue(inspect(self.root)['errors'])
        self.t.observe_minute(NOW,g.MINUTE_IDS,NOW);self.t.observe_scan(NOW,100)
        self.assertFalse(inspect(self.root)['errors'])


def g3_universe():
    from strategies.generation_three import EQUITIES,COMMODITIES
    return set(EQUITIES)|set(COMMODITIES)
