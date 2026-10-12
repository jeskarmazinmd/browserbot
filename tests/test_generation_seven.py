import ast,json,os,subprocess,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
from engine.events import MarketSnapshot,Quote
from strategies import generation_seven as g
from generation_seven_paper_tracker import GenerationSevenBidAskTracker,FILE_STEM
from reporting.generation_seven_performance import calculate_generation_seven
from tests.test_generation_five import book
NOW=datetime(2026,10,12,17,15,tzinfo=timezone.utc)
def signal(sid='G7ROTPROTECT',now=NOW):
 s=g._BY_ID[sid];parent=g.PARENTS[s.family][0]
 e=dict(ret5=.3,ret1=.1,excess=.5,breadth=.8,breadth5=.8,leaders=['GLD']*3,parent_evidence=dict(best_return=1.,breadth=.8))
 return dict(strategy_id=sid,symbol='GLD',timestamp=now.isoformat(),completed_minute=(now-timedelta(minutes=1)).isoformat(),entry_price=100.,target_price=101.,stop_price=99.25,paper_only=True,live_order_placement=False,rule_version=g.RULE_VERSION,population_hash=g.POPULATION_HASH,rule_source_sha256=g.RULE_SOURCE_SHA256,constituent_votes=[parent],admission_evidence=e,exit_model='target_stop_eod')
def tracker(root):return GenerationSevenBidAskTracker(root,now_provider=lambda:NOW)
class Tests(unittest.TestCase):
 def test_historical_prefix_allows_append_but_detects_rewrite(self):
  import hashlib
  from research_tools.g7.verify_production import prefix_matches
  with tempfile.TemporaryDirectory() as root:
   p=Path(root,'ledger');record=dict(bytes=3,sha256=hashlib.sha256(b'abc').hexdigest())
   p.write_bytes(b'abc appended');self.assertTrue(prefix_matches(p,record))
   p.write_bytes(b'ab');self.assertFalse(prefix_matches(p,record))
   p.write_bytes(b'xyz appended');self.assertFalse(prefix_matches(p,record))
 def test_missing_or_changed_manifest_is_not_reset(self):
  for kind in ('missing','changed'):
   with tempfile.TemporaryDirectory() as root:
    t=tracker(root);p=Path(root,FILE_STEM+'_manifest.json')
    if kind=='missing':p.unlink()
    else:p.write_text('{}')
    with self.assertRaises(ValueError):tracker(root)
 def test_population_and_owned_evaluators(self):
  self.assertEqual(g.ALL_IDS,{'G7ROTPROTECT','G7BRDSTABLE'});self.assertFalse(g.IDS)
  a=g.Strategy('G7ROTPROTECT');b=g.Strategy('G7ROTPROTECT');self.assertIsNot(a.parent,b.parent)
  for sid in g.ALL_IDS:
   self.assertTrue(g.metadata(sid)['paper_only']);self.assertFalse(g.metadata(sid)['config']['live_order_placement'])
 def test_executable_partial_exit_and_no_book_reuse(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);self.assertTrue(t.register_signal(signal(),book(NOW,size=10),NOW))
   r=next(iter(t.active.values()));self.assertEqual(r['filled_qty'],10);self.assertEqual(r['entry_price'],100.)
   later=NOW+timedelta(seconds=1);q=book(later,bid=101.,ask=101.01,size=4)
   self.assertEqual(t.update_quotes({'GLD':q},later),[]);self.assertEqual(r['remaining_qty'],6)
   restored=tracker(root);self.assertEqual(restored.update_quotes({'GLD':q},later),[])
   rows=restored.update_quotes({'GLD':book(later+timedelta(seconds=1),bid=101.,ask=101.01,size=10)},later+timedelta(seconds=1))
   self.assertEqual(rows[0]['pnl'],10.);self.assertIn('execution_evidence',rows[0]);self.assertFalse(rows[0]['broker_execution_enabled'])
 def test_profit_protection_persists_and_fills_actual_bid(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);t.register_signal(signal(),book(NOW),NOW)
   t.update_quotes({'GLD':book(NOW+timedelta(seconds=1),bid=100.8,ask=100.81)},NOW+timedelta(seconds=1))
   t=tracker(root)
   later=NOW+timedelta(seconds=2);rows=t.update_quotes({'GLD':book(later,bid=100.4,ask=100.41)},later)
   self.assertEqual(rows[0]['exit_reason'],'G7_PROFIT_PROTECT');self.assertEqual(rows[0]['exit_price'],100.4)
 def test_gap_stop_and_stale_or_future_book_never_fill(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);t.register_signal(signal(),book(NOW),NOW);later=NOW+timedelta(seconds=20)
   self.assertEqual(t.update_quotes({'GLD':book(later+timedelta(seconds=1),bid=105.,ask=105.01)},later),[])
   self.assertIsNone(next(iter(t.active.values())).get('pending_exit_reason'))
   self.assertEqual(t.update_quotes({'GLD':book(NOW,bid=98.,ask=98.01)},later),[])
   rows=t.update_quotes({'GLD':book(later,bid=98.,ask=98.01)},later)
   self.assertEqual(rows[0]['exit_reason'],'STOP');self.assertEqual(rows[0]['exit_price'],98.)
 def test_birth_manifest_corruption_and_cooldown(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);births=t.births.copy()
   self.assertFalse(t.register_signal(signal(now=NOW-timedelta(minutes=1)),book(NOW),NOW))
   self.assertTrue(t.register_signal(signal(),book(NOW),NOW))
   t.update_quotes({'GLD':book(NOW+timedelta(seconds=1),bid=101.,ask=101.01)},NOW+timedelta(seconds=1))
   t=tracker(root);self.assertEqual(t.births,births)
   later=NOW+timedelta(minutes=20);self.assertFalse(t.register_signal(signal(now=later),book(later),later))
   with t.ledger_path.open('a') as f:f.write('{invalid\n')
   with self.assertRaises(ValueError):tracker(root)
 def test_same_parent_setup_does_not_merge_accounts(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root)
   for sid in g.ALL_IDS:
    s=signal(sid);s['setup_id']='parent-shared';self.assertTrue(t.register_signal(s,book(NOW),NOW))
   self.assertEqual(len(t.active),2)
 def test_paper_contract_future_features_and_wrong_admission_rejected(self):
  for kind in ('broker','future','rule','evidence','stale'):
   with tempfile.TemporaryDirectory() as root:
    t=tracker(root);s=signal('G7BRDSTABLE');q=book(NOW)
    if kind=='broker':s['live_order_placement']=True
    if kind=='future':s['completed_minute']=NOW.isoformat()
    if kind=='rule':s['population_hash']='wrong'
    if kind=='evidence':s['admission_evidence']['breadth5']=.2
    if kind=='stale':q=book(NOW-timedelta(seconds=6))
    self.assertFalse(t.register_signal(s,q,NOW),kind)
 def test_report_uses_actual_quantities_and_unknown_marks(self):
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);t.register_signal(signal(),book(NOW,size=10),NOW)
   mods,diag=calculate_generation_seven(Path(root),'2026-10-12',NOW,{},lambda s,c:book(NOW,bid=99.9,ask=100.))
   self.assertAlmostEqual(mods['G7ROTPROTECTBA']['pnl'],-1.)
   mods,diag=calculate_generation_seven(Path(root),'2026-10-12',NOW+timedelta(seconds=6),{},lambda s,c:book(NOW))
   self.assertNotIn('G7ROTPROTECTBA',mods);self.assertEqual(diag['unmarked'],1)
 def test_registry_opt_in_and_runner_route(self):
  for flag,count in [('0',0),('1',2)]:
   code='from strategies import registry as r,generation_seven as g; print(sum(s.name in g.ALL_IDS for s in r.MINUTE_STRATEGIES),len(r.FAILED_STRATEGIES))'
   p=subprocess.run([sys.executable,'-c',code],env={**os.environ,'ENABLE_G7_PAPER':flag},capture_output=True,text=True,check=True)
   self.assertEqual(p.stdout.strip().splitlines()[-1],f'{count} 0')
  path=Path('live_strategy_runner.py');fn=next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
  env=dict(RUN_MODE='LIVE',G7_ENABLED=True,GENERATION_SEVEN_IDS=g.ALL_IDS,generation_seven_outcomes=Mock(),independent_l1=Mock(),quote_source=Mock())
  env['independent_l1'].quotes.return_value={'GLD':book(NOW)};env['quote_source'].now.return_value=NOW
  exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
  env['register_single_leg_paper'](signal());env['generation_seven_outcomes'].register_signal.assert_called_once()
  for mode,flag in [('REPLAY',True),('LIVE',False)]:
   env.update(RUN_MODE=mode,G7_ENABLED=flag);self.assertFalse(env['register_single_leg_paper'](signal()))
 def test_causal_completed_minute_emission_and_gap_reset(self):
  strategy=g.Strategy('G7BRDSTABLE');events=[]
  for i in range(20):
   t=NOW+timedelta(minutes=i);q={s:Quote(100*(1.001**i)) for s in g.POOL};snap=MarketSnapshot(t,q,len(q),len(q),0);events+=strategy.on_snapshot(snap)
  self.assertTrue(events)
  for e in events:self.assertEqual(e.timestamp,datetime.fromisoformat(e.data['completed_minute'])+timedelta(minutes=1))
  snap=MarketSnapshot(NOW+timedelta(minutes=30),q,len(q),len(q),0);self.assertEqual(strategy.on_snapshot(snap),[])
 def test_replay_runtime_same_fills_for_gap_and_profit_protection(self):
  from research_tools.g7.replay import Portfolio
  from engine.events import SignalEvent
  with tempfile.TemporaryDirectory() as root:
   t=tracker(root);p=Portfolio('ROT','PROTECT');s=signal();e=SignalEvent(NOW,'G7ROTPROTECT','GLD','SIGNAL',s)
   t.register_signal(s,book(NOW),NOW);p.enter(e,{'GLD':book(NOW)},NOW)
   for seconds,bid in [(1,100.8),(2,100.4)]:
    now=NOW+timedelta(seconds=seconds);q={'GLD':book(now,bid=bid,ask=bid+.01)};rows=t.update_quotes(q,now);p.mark(q,now)
   self.assertAlmostEqual(rows[0]['pnl'],p.trades[0]['pnl'])
if __name__=='__main__':unittest.main()
