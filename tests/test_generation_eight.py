import ast,json,os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from types import SimpleNamespace
from engine.events import MarketSnapshot,Quote
from strategies import generation_eight as g
from strategies.generation_eight_retirement import report_ids
from generation_eight_paper_tracker import GenerationEightBidAskTracker as Tracker,FILE_STEM
from reporting.generation_eight_performance import calculate_generation_eight
from reporting.cutoff_quotes import frozen_books

NOW=datetime(2026,10,14,16,0,tzinfo=timezone.utc)
def book(now=NOW,bid=99.99,ask=100.,size=1000):
    stamp=now.timestamp()*1000
    return dict(bid=bid,ask=ask,bid_size_raw=size,ask_size_raw=size,bid_time_ms=stamp,ask_time_ms=stamp,quote_time_ms=stamp,realtime=True)
def evidence(sid):
    return {'price':100.,'ret1':.1,'ret3':.2,'ret5':.3,'lagged_scale':.01,g.GATES[g.spec_for(sid).mechanism_code]:True}
def signal(sid='G8T01TECH',now=NOW,symbol=None):
    s=g.spec_for(sid);return g.signal_row(s,symbol or s.universe[0],evidence(sid),now-timedelta(minutes=1))

class Tests(unittest.TestCase):
    def setUp(self):self.root=tempfile.TemporaryDirectory();self.t=Tracker(self.root.name,now_provider=lambda:NOW)
    def tearDown(self):self.t.close();self.root.cleanup()
    def test_population_and_route_novelty(self):
        self.assertEqual(len(g.CATALOG),120);self.assertEqual(len(g.GATES),30);self.assertFalse(g.IDS)
        self.assertEqual(len({(s.mechanism_code,s.route,s.universe,s.leaders) for s in g.CATALOG}),120)
        for s in g.CATALOG:
            self.assertEqual(s.equity,5000);self.assertEqual(s.notional,1000)
            self.assertFalse(g.metadata(s.strategy_id)['config']['live_order_placement'])
            self.assertTrue(g.metadata(s.strategy_id)['paper_only'])
    def test_fractional_price_geometry_has_no_roundoff_rejection(self):
        for i,s in enumerate(g.CATALOG[:8]):
            price=94.13+i*.07
            self.assertTrue(self.t.register_signal(signal(s.strategy_id),book(bid=price-.01,ask=price),NOW))
    def test_all_120_reachable_separate_executable_accounts(self):
        for s in g.CATALOG:
            self.assertTrue(g.admission_accepts(s.strategy_id,evidence(s.strategy_id),s.universe[0]))
            self.assertTrue(self.t.register_signal(signal(s.strategy_id),book(),NOW),s.strategy_id)
        self.assertEqual(len(self.t.active),120)
        self.assertEqual(len({r['strategy_id'] for r in self.t.active.values()}),120)
        self.assertTrue(all(r['filled_qty']==10 for r in self.t.active.values()))
    def test_each_mechanism_evidence_contrast(self):
        for s in g.CATALOG:
            e=evidence(s.strategy_id);self.assertTrue(g.admission_accepts(s.strategy_id,e,s.universe[0]))
            e[g.GATES[s.mechanism_code]]=False;self.assertFalse(g.admission_accepts(s.strategy_id,e,s.universe[0]))
            e=evidence(s.strategy_id);e['ret1']=float('nan');self.assertFalse(g.admission_accepts(s.strategy_id,e,s.universe[0]))
    def test_feature_store_uses_completed_contiguous_paths(self):
        store=g.FeatureStore();start=NOW-timedelta(minutes=100)
        for i in range(96):
            snap=MarketSnapshot(start+timedelta(minutes=i),{s:Quote(100*(1+.0001*(1+list(sorted(g.SYMBOLS)).index(s)%4))**i) for s in g.SYMBOLS},len(g.SYMBOLS),len(g.SYMBOLS),0)
            features=store.features(snap,'TECH')
        self.assertEqual(set(features),set(g.ROUTES['TECH'][0]))
        old=json.dumps(features,sort_keys=True);self.assertEqual(old,json.dumps(store.features(snap,'TECH'),sort_keys=True))
        missing=MarketSnapshot(snap.timestamp+timedelta(minutes=1),{},0,0,0)
        self.assertFalse(store.features(missing,'TECH'))
        self.assertFalse(store.features(snap,'TECH'))
    def test_session_gap_future_order_and_duplicate_emission(self):
        strategy=g.Strategy('G8T01TECH',store=Mock())
        strategy.store.features.return_value={'NVDA':evidence('G8T01TECH')}
        snap=MarketSnapshot(NOW-timedelta(minutes=1),{},0,0,0)
        a=strategy.on_snapshot(snap);self.assertEqual(len(a),1);self.assertEqual(a[0].timestamp,NOW)
        self.assertFalse(strategy.on_snapshot(snap))
        strategy.store.features.return_value={}
        self.assertFalse(strategy.on_snapshot(MarketSnapshot(NOW,{},0,0,0)))
        self.assertFalse(strategy.on_snapshot(MarketSnapshot(NOW-timedelta(minutes=2),{},0,0,0)))
    def test_quote_and_contract_fail_closed(self):
        for name in ['stale','future','empty','delayed','contract','rule','causal','universe']:
            with self.subTest(name=name):
                sid='G8T01TECH';row=signal(sid,now=NOW+timedelta(minutes=len(self.t.seen)))
                now=datetime.fromisoformat(row['timestamp']);q=book(now)
                if name=='stale':q=book(now-timedelta(seconds=2))
                if name=='future':q=book(now+timedelta(milliseconds=1))
                if name=='empty':q=book(now,size=0)
                if name=='delayed':q['realtime']=False
                if name=='contract':row['live_order_placement']=True
                if name=='rule':row['population_hash']='bad'
                if name=='causal':row['completed_minute']=now.isoformat()
                if name=='universe':row['symbol']='UNAPPROVED'
                self.assertFalse(self.t.register_signal(row,q,now))
        self.assertFalse(self.t.active)
    def test_birth_provenance_and_writer_lock(self):
        with self.assertRaises(ValueError):Tracker(self.root.name,now_provider=lambda:NOW)
        self.assertFalse(self.t.register_signal(signal(now=NOW-timedelta(minutes=1)),book(),NOW))
        birth=self.t.births.copy();self.t.close();self.t=Tracker(self.root.name,now_provider=lambda:NOW+timedelta(days=1))
        self.assertEqual(self.t.births,birth)
    def test_symbol_cap_and_cash_budget(self):
        sid='G8T01TECH'
        for i,symbol in enumerate(g.spec_for(sid).universe[:5]):
            self.assertTrue(self.t.register_signal(signal(sid,symbol=symbol),book(),NOW))
        self.assertFalse(self.t.register_signal(signal(sid,symbol=g.spec_for(sid).universe[5]),book(),NOW))
        self.assertFalse(self.t.register_signal(signal(sid,now=NOW+timedelta(minutes=1)),book(NOW+timedelta(minutes=1)),NOW+timedelta(minutes=1)))
        self.assertAlmostEqual(self.t._cash_for(sid,NOW)[1],0)
        self.assertLessEqual(sum(r['notional'] for r in self.t.active.values()),5000)
    def test_partial_book_consumption_survives_restart(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW));later=NOW+timedelta(seconds=10)
        q=book(later,bid=101.,ask=101.01,size=40)
        self.assertEqual(self.t.update_quotes({'NVDA':q},later),[])
        self.assertEqual(next(iter(self.t.active.values()))['remaining_qty'],6)
        self.t.close();self.t=Tracker(self.root.name,now_provider=lambda:NOW)
        self.assertEqual(self.t.update_quotes({'NVDA':q},later),[])
        self.assertEqual(next(iter(self.t.active.values()))['remaining_qty'],6)
        closed=self.t.update_quotes({'NVDA':book(later+timedelta(seconds=1),bid=101.,ask=101.01)},later+timedelta(seconds=1))
        self.assertEqual(closed[0]['remaining_qty'],0);self.assertAlmostEqual(closed[0]['pnl'],10.)
        self.t.close();self.t=Tracker(self.root.name,now_provider=lambda:NOW)
        self.assertFalse(self.t.active);self.assertAlmostEqual(self.t._daily_realized[('G8T01TECH','2026-10-14')],10.)
    def test_gap_loss_brake_is_durable_and_exits_continue(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW));later=NOW+timedelta(seconds=10)
        closed=self.t.update_quotes({'NVDA':book(later,bid=80.,ask=80.01)},later)
        self.assertEqual(len(closed),1);self.assertAlmostEqual(closed[0]['pnl'],-200.)
        self.assertIn(('G8T01TECH','2026-10-14'),self.t._braked)
        self.t.close();self.t=Tracker(self.root.name,now_provider=lambda:NOW)
        now=NOW+timedelta(minutes=40)
        self.assertFalse(self.t.register_signal(signal(now=now),book(now),now))
    def test_carry_blocks_new_cash_and_report_is_unknown(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW));nextday=NOW+timedelta(days=1)
        self.t.update_quotes({},nextday)
        self.assertAlmostEqual(self.t._cash_for('G8T01TECH',nextday)[1],4000.)
        self.assertFalse(self.t.register_signal(signal(now=nextday,symbol='AMD'),book(nextday),nextday))
        rows,d=calculate_generation_eight(Path(self.root.name),'2026-10-15',nextday,{},lambda s,m:book(nextday))
        self.assertIsNone(rows['G8T01TECHBA']['return_pct'])
    def test_timeout_requests_partial_exit_without_fabricating_fill(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW));later=NOW+timedelta(minutes=31)
        self.assertFalse(self.t.update_quotes({'NVDA':book(later,size=0)},later))
        self.assertEqual(len(self.t.active),1)
        closed=self.t.update_quotes({'NVDA':book(later+timedelta(seconds=1))},later+timedelta(seconds=1))
        self.assertEqual(closed[0]['exit_reason'],'G8_MAX_HOLD')
    def test_malformed_ledger_is_preserved_and_recovery_fails(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW));self.t.close()
        p=Path(self.root.name,FILE_STEM+'_outcomes.jsonl');p.write_text(p.read_text()+'{bad\n');before=p.read_bytes()
        with self.assertRaises(ValueError):Tracker(self.root.name,now_provider=lambda:NOW)
        self.assertEqual(p.read_bytes(),before)
    def test_reporting_actual_quantities_and_missing_marks(self):
        self.assertTrue(self.t.register_signal(signal(),book(),NOW))
        rows,d=calculate_generation_eight(Path(self.root.name),'2026-10-14',NOW,{},lambda s,m:{})
        self.assertIsNone(rows['G8T01TECHBA']['return_pct']);self.assertEqual(len(rows),120)
        later=NOW+timedelta(seconds=1);self.t.update_quotes({'NVDA':book(later,bid=101.,ask=101.01)},later)
        rows,d=calculate_generation_eight(Path(self.root.name),'2026-10-14',later,{},lambda s,m:{})
        self.assertAlmostEqual(rows['G8T01TECHBA']['return_pct'],.2);self.assertEqual(rows['G8T01TECHBA']['closed_taken'],1)
    def test_live_routing_never_falls_into_broker_or_parent_tracker(self):
        p=Path('live_strategy_runner.py');fn=next(n for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
        env=dict(RUN_MODE='LIVE',G8_ENABLED=True,GENERATION_EIGHT_IDS=g.ALL_IDS,generation_eight_outcomes=Mock(),independent_l1=Mock(),quote_source=Mock())
        env['independent_l1'].quotes.return_value={'NVDA':book()};env['quote_source'].now.return_value=NOW
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),env)
        env['register_single_leg_paper'](signal());env['generation_eight_outcomes'].register_signal.assert_called_once()
        for mode,flag in [('REPLAY',True),('LIVE',False)]:
            env.update(RUN_MODE=mode,G8_ENABLED=flag);self.assertFalse(env['register_single_leg_paper'](signal()))
        self.assertFalse(env['register_single_leg_paper']({'strategy_id':'G8_UNKNOWN'}))
    def test_exact_reversible_retirement_and_live_protection(self):
        with patch.dict(os.environ,{'ENABLE_G8_RETIREMENTS':'1','LIVE_STRATEGY_ID':''}):self.assertEqual(len(report_ids()),26)
        with patch.dict(os.environ,{'ENABLE_G8_RETIREMENTS':'0'}):self.assertFalse(report_ids())
        with patch.dict(os.environ,{'ENABLE_G8_RETIREMENTS':'1','LIVE_STRATEGY_ID':'PMID'}):
            with self.assertRaises(ValueError):report_ids()
    def test_historical_marks_cannot_use_current_live_book(self):
        p=Path(self.root.name,'live_l1_snapshot.json');p.write_text(json.dumps({'collector_observed_at':(NOW+timedelta(days=1)).isoformat(),'quotes':{'NVDA':book(NOW+timedelta(days=1))}}))
        self.assertFalse(frozen_books(Path(self.root.name),'2026-10-14',NOW))
    def test_retired_main_output_keeps_existing_exit_service(self):
        from bidask_paper_outcome_tracker import IndependentBidAskPaperTracker
        old=IndependentBidAskPaperTracker(self.root.name)
        row=dict(strategy_id='PMID',symbol='NVDA',timestamp=NOW.isoformat(),entry_price=100.,target_price=101.,stop_price=98.)
        with patch.dict(os.environ,{'ENABLE_G8_RETIREMENTS':'0'}):self.assertTrue(old.register_signal(row,book(),NOW))
        with patch.dict(os.environ,{'ENABLE_G8_RETIREMENTS':'1','LIVE_STRATEGY_ID':''}):
            self.assertFalse(old.register_signal({**row,'timestamp':(NOW+timedelta(minutes=1)).isoformat()},book(NOW+timedelta(minutes=1)),NOW+timedelta(minutes=1)))
            exits=old.update_quotes({'NVDA':book(NOW+timedelta(seconds=1),bid=102.,ask=102.01)},NOW+timedelta(seconds=1))
            self.assertEqual(len(exits),1);self.assertFalse(old.active)
    def test_checkpoint_preserves_original_bytes_and_archive(self):
        from research_tools.g8.preserve import preserve
        import zipfile,hashlib
        root=Path(self.root.name);ledger=root/'paper_example_outcomes.jsonl';ledger.write_text('{"event":"historical"}\n')
        original=ledger.read_bytes();(root/'all_engine_bidask_daily_history.json').write_text(json.dumps({'version':3,'days':{'2026-10-12':{'modules':{'OLD':{'return_pct':1.}}}}}))
        r=preserve(root,Path('.'));self.assertEqual(ledger.read_bytes(),original)
        with zipfile.ZipFile(r['archive']) as z:
            self.assertIsNone(z.testzip());self.assertEqual(z.read('data/paper_example_outcomes.jsonl'),original)
            m=json.loads(z.read('preservation_manifest.json'));self.assertEqual(m['ledger_prefixes'][ledger.name]['sha256'],hashlib.sha256(original).hexdigest())
    def test_quote_union_is_research_only_and_survives_exit_only_mode(self):
        code=Path('live_quote_collector.py').read_text();fn=next(n for n in ast.walk(ast.parse(code)) if isinstance(n,ast.FunctionDef) and n.name=='load_symbols')
        root=Path(self.root.name);today=NOW.strftime('%Y%m%d');p=root/('research_universe_'+today+'.csv');p.write_text('symbol,legacy_eligible\nAAPL,True\nOTHER,False\n');before=p.read_bytes()
        def local_path(v):
            value=str(v)
            if value in ('/data','/app','.'):return root
            if value.startswith('/data/') or value.startswith('/app/'):return root/Path(value).name
            return Path(value)
        env=dict(Path=local_path,datetime=SimpleNamespace(now=lambda tz:NOW),timezone=timezone,os=os,_write_universe_status=Mock())
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'collector_fixture','exec'),env)
        with patch.dict(os.environ,{'ENABLE_G8_PAPER':'1'}):self.assertTrue(g.SYMBOLS<=set(env['load_symbols']()))
        self.assertEqual(p.read_bytes(),before)
        (root/'paper_generation_eight_bidask_independent_births.json').write_text('{}')
        with patch.dict(os.environ,{'ENABLE_G8_PAPER':'0'}):self.assertTrue(g.SYMBOLS<=set(env['load_symbols']()))

if __name__=='__main__':unittest.main()
