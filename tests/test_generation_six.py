import ast,json,os,subprocess,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
from engine.events import MarketSnapshot,Quote
from strategies import generation_six as g
from strategies import generation_six_retirement as retire
from generation_six_paper_tracker import GenerationSixBidAskTracker,FILE_STEM
from reporting.generation_six_performance import calculate_generation_six
from tests.test_generation_five import book
NOW=datetime(2026,10,12,16,0,tzinfo=timezone.utc)

def evidence(s):
 return dict(price=100.,ret=1.5,r2=.9,ret5=.3,ret1=.25,excess=1.25,spy_return=.25,
             breakout=.2,prior_range=.5,had_dip=True)
def signal(sid='G6R01CTL',now=NOW,symbol='QQQ'):
 s=g.spec_for(sid);e=evidence(s)
 if s.architecture=='PULLBACK':e['ret5']=-.2
 if sid in g.IDS:
  e=dict(pre_return_pct=1.5,pre_r2=.9,flash_drop_pct=2.,pre30_return_std_pct=.4)
  original=4. if s.architecture=='LOWPRICE' else 104.
  price=3.93 if s.architecture=='LOWPRICE' else 102.
  row=g.MODULES[sid].refresh_event_for_entry(dict(e,target_price=original,timestamp=now.isoformat()),price)
 else:
  row=g.signal_row(s,100.,100.,e);row['completed_minute']=now.isoformat()
 row.update(strategy_id=sid,symbol=symbol,timestamp=now.isoformat())
 return row

def tracker(root):return GenerationSixBidAskTracker(root,now_provider=lambda:NOW)
class Tests(unittest.TestCase):
 def test_all_400_have_reachable_independent_admissions(self):
  from benchmarks.benchmark_generation_six import tracker_benchmark
  self.assertEqual(tracker_benchmark()['accepted'],400)
 def test_population_metadata_and_behavior_fingerprints(self):
  self.assertEqual(len(g.CATALOG),400);self.assertEqual(len(g.IDS),240);self.assertEqual(len(g.MINUTE_IDS),160)
  self.assertEqual(len({g.semantic_key(s) for s in g.CATALOG}),400)
  for s in g.CATALOG:
   self.assertTrue(g.metadata(s.strategy_id)['paper_only']);self.assertFalse(g.metadata(s.strategy_id)['config']['live_order_placement'])
   self.assertTrue(s.hypothesis and s.source and s.universe);self.assertEqual(s.equity,5000.)
   self.assertLessEqual(s.notional,1000.);self.assertEqual(s.max_position_fraction,.2)
 def test_exact_retirement_and_protected_sources(self):
  with patch.dict(os.environ,{'ENABLE_G6_PAPER':'1'}):
   p=retire.plan();self.assertEqual(len(retire.report_retired_ids()),400)
   self.assertTrue(all(not retire.entry_retired(s) for s in p['retained_report_ids']))
   self.assertTrue(retire.entry_retired('A'));self.assertNotIn('A',retire.evaluation_retired_ids())
   self.assertTrue(retire.entry_retired('G5TRCTL'));self.assertFalse(retire.entry_retired('G6R01CTL'))
 def test_registry_opt_in_filters_both_cadences(self):
  code="from strategies import registry as r,generation_six as g; from strategies.generation_six_retirement import evaluation_retired_ids; print(sum(s in g.IDS for s in r.FLASH_STRATEGY_MODULES),sum(s.name in g.MINUTE_IDS for s in r.MINUTE_STRATEGIES),len(r.FAILED_STRATEGIES),len(set(r.FLASH_STRATEGY_MODULES)&evaluation_retired_ids()),len({s.name for s in r.MINUTE_STRATEGIES}&evaluation_retired_ids()))"
  for flag,expected in [('0',[0,0,0,0,0]),('1',[240,160,0,0,0])]:
   result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'ENABLE_G3_PAPER':'1','ENABLE_G4_PAPER':'1','ENABLE_G5_PAPER':'1','ENABLE_G6_PAPER':flag},capture_output=True,text=True,check=True)
   self.assertEqual(list(map(int,result.stdout.strip().splitlines()[-1].split())),expected)
 def test_runner_only_paper_tracker_not_broker(self):
  path=Path('live_strategy_runner.py');fn=next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
  env=dict(RUN_MODE='LIVE',G6_ENABLED=True,GENERATION_SIX_IDS=g.ALL_IDS,GENERATION_ONE_IDS=set(),GENERATION_TWO_IDS=set(),GENERATION_THREE_IDS=set(),GENERATION_FOUR_IDS=set(),GENERATION_FIVE_IDS=set(),generation_six_outcomes=Mock(),independent_ba_outcomes=Mock(),paper_outcomes=Mock(),independent_l1=Mock(),quote_source=Mock())
  env['independent_l1'].quotes.return_value={'QQQ':book(NOW)};env['quote_source'].now.return_value=NOW
  exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
  env['register_single_leg_paper'](signal());env['generation_six_outcomes'].register_signal.assert_called_once()
  for mode,flag in [('REPLAY',True),('LIVE',False)]:
   env.update(RUN_MODE=mode,G6_ENABLED=flag);self.assertFalse(env['register_single_leg_paper'](signal()))
  env['independent_ba_outcomes'].register_signal.assert_not_called();env['paper_outcomes'].register.assert_not_called()
 def test_actual_ask_bid_fill_and_capital(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);self.assertTrue(t.register_signal(signal(),book(NOW),NOW))
   row=next(iter(t.active.values()));self.assertEqual(row['entry_price'],100.);self.assertLessEqual(row['notional'],1000.)
   self.assertLessEqual(row['filled_qty'],250);later=NOW+timedelta(seconds=20)
   closed=t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01)},later)
   self.assertEqual(closed[0]['exit_price'],101.);self.assertIn('execution_evidence',closed[0])
   self.assertEqual(closed[0]['pnl'],closed[0]['filled_qty'])
   rows,_=calculate_generation_six(Path(root),'2026-10-12',later,{},lambda s,m:book(later,bid=101.,ask=101.01))
   self.assertEqual(rows['G6R01CTLBA']['pnl'],closed[0]['pnl']);self.assertEqual(len(rows),400)
 def test_stale_future_zero_liquidity_and_bad_contract(self):
  for kind in ('stale','future','empty','contract','evidence'):
   with tempfile.TemporaryDirectory() as root:
    t=tracker(root);s=signal();q=book(NOW)
    if kind=='stale':q=book(NOW-timedelta(seconds=4))
    if kind=='future':q=book(NOW+timedelta(seconds=1))
    if kind=='empty':q=book(NOW,size=0)
    if kind=='contract':s['live_order_placement']=True
    if kind=='evidence':s['admission_evidence']['excess']=0
    self.assertFalse(t.register_signal(s,q,NOW),kind);self.assertFalse(t.active)
 def test_prospective_recovery_manifest_and_partial_book(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);births=t.births.copy()
   self.assertFalse(t.register_signal(signal(now=NOW-timedelta(minutes=1)),book(NOW),NOW))
   self.assertTrue(t.register_signal(signal(),book(NOW,size=8),NOW))
   row=next(iter(t.active.values()));self.assertEqual(row['filled_qty'],2)
   later=NOW+timedelta(seconds=1);q=book(later,bid=101.,ask=101.01,size=4)
   self.assertEqual(t.update_quotes({'QQQ':q},later),[]);self.assertEqual(next(iter(t.active.values()))['remaining_qty'],1)
   restored=tracker(root);self.assertEqual(restored.births,births)
   self.assertEqual(restored.update_quotes({'QQQ':q},later),[])
   closed=restored.update_quotes({'QQQ':book(later+timedelta(seconds=1),bid=101.,ask=101.01,size=4)},later+timedelta(seconds=1))
   self.assertEqual(closed[0]['remaining_qty'],0)
   with Path(root,FILE_STEM+'_outcomes.jsonl').open('a') as f:f.write('{bad\n')
   with self.assertRaises(ValueError):tracker(root)
 def test_flash_owned_admission_and_no_symbol_stacking(self):
  for sid in ('G6M01CTL','G6L01CTL','G6V01CTL'):
   with tempfile.TemporaryDirectory() as root:
    t=tracker(root);s=signal(sid);price=s['entry_price'];q=book(NOW,bid=price-.001,ask=price)
    self.assertTrue(t.register_signal(s,q,NOW),sid)
    s=signal(sid,now=NOW+timedelta(minutes=1));self.assertFalse(t.register_signal(s,book(NOW+timedelta(minutes=1),bid=price-.001,ask=price),NOW+timedelta(minutes=1)))
 def test_minute_rules_missing_data_and_no_future_features(self):
  for sid in sorted(g.MINUTE_IDS):
   s=g.spec_for(sid);e=evidence(s)
   if s.architecture=='PULLBACK':e['ret5']=-.2
   self.assertTrue(g.minute_admits(s,e),sid)
  store=g.FeatureStore();s=g.MinuteStrategy('G6R01CTL',store)
  for i in range(35):
   now=NOW+timedelta(minutes=i);p=100*(1.0004**i)
   q={sym:Quote(p if sym=='SPY' else 100*(1.001**i)) for sym in g.EQUITIES}
   snap=MarketSnapshot(now,q,len(q),len(q),0);s.on_snapshot(snap)
  self.assertTrue(s.on_snapshot(snap))
  gap=MarketSnapshot(NOW+timedelta(minutes=40),q,len(q),len(q),0)
  self.assertEqual(s.on_snapshot(gap),[])
 def test_retired_tracker_bypass_rejected_history_kept(self):
  from generation_five_paper_tracker import GenerationFiveBidAskTracker
  from tests.test_generation_five import signal as old_signal,NOW as old_now,book as old_book
  with tempfile.TemporaryDirectory() as root:
   t=GenerationFiveBidAskTracker(root,now_provider=lambda:old_now)
   self.assertTrue(t.register_signal(old_signal(),old_book(),old_now))
   size=t.ledger_path.stat().st_size
   with patch.dict(os.environ,{'ENABLE_G6_PAPER':'1'}):
    self.assertFalse(t.register_signal(old_signal(now=old_now+timedelta(minutes=1)),old_book(),old_now+timedelta(minutes=1)))
    self.assertEqual(t.ledger_path.stat().st_size,size);self.assertEqual(len(t.active),1)
 def test_shared_parent_setup_cannot_deduplicate_siblings(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root)
   for sid in ('G6R01CTL','G6R01PATIENT'):
    row=signal(sid);row['setup_id']='PARENT|QQQ|same'
    self.assertTrue(t.register_signal(row,book(NOW),NOW))
   self.assertEqual(len(t.active),2)
 def test_max_hold_uses_fill_time_and_rejects_stale_exit(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);self.assertTrue(t.register_signal(signal('G6R01PATIENT'),book(NOW),NOW))
   later=NOW+timedelta(seconds=1801)
   self.assertEqual(t.update_quotes({'QQQ':book(NOW)},later),[])
   rows=t.update_quotes({'QQQ':book(later)},later)
   self.assertEqual(rows[0]['exit_reason'],'G6_MAX_HOLD')
 def test_native_retirement_tracker_bypasses(self):
  from forex_paper_tracker import ForexPaperTracker
  from statarb_paper_tracker import StatArbPaperTracker
  from short_paper_tracker import ShortPaperTracker
  from microstructure_paper_tracker import MicrostructurePaperTracker
  with patch.dict(os.environ,{'ENABLE_G6_PAPER':'1'}),tempfile.TemporaryDirectory() as root:
   for cls,sid in [(ForexPaperTracker,'FXAUD1'),(StatArbPaperTracker,'STSECTOR1'),(ShortPaperTracker,'SHTMKT1'),(MicrostructurePaperTracker,'MSSPSHOCK1')]:
    t=cls(root);t.open_decisions([{'strategy_id':sid}]);self.assertFalse(t.active)
if __name__=='__main__':unittest.main()
