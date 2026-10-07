from datetime import datetime,timedelta,timezone
import ast
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
from engine.events import MarketSnapshot,Quote
from generation_four_paper_tracker import GenerationFourBidAskTracker,FILE_STEM
from reporting.generation_four_performance import calculate_generation_four
from strategies import generation_four as g4
from research_tools.g4_review.evidence import review
from research_tools.g4_review.report import build

NOW=datetime(2026,10,8,16,0,tzinfo=timezone.utc)
SID='G4RREVINDEX'
def book(now=NOW,bid=99.99,ask=100.,size=1000):
    return dict(bid=bid,ask=ask,bid_size_raw=size,ask_size_raw=size,
                bid_time_ms=now.timestamp()*1000,ask_time_ms=now.timestamp()*1000,realtime=True)
def signal(sid=SID,now=NOW,setup='a'):
    s=g4.spec_for(sid)
    return dict(strategy_id=sid,symbol=s.universe[0],timestamp=now.isoformat(),
                completed_minute=now.isoformat(),setup_id=setup,entry_price=100.,
                target_price=100.6,stop_price=99.6,paper_only=True,live_order_placement=False,
                rule_version=g4.RULE_VERSION,population_hash=g4.POPULATION_HASH,rule_source_sha256=g4.RULE_SOURCE_SHA256,
                admission_evidence={'z':-3,'fit_return_count':45},constituent_votes=[s.mechanism])
def snap(now,prices):
    return MarketSnapshot(now,{s:Quote(p) for s,p in prices.items()},len(prices),len(prices),0.)

class G4Tests(unittest.TestCase):
    def tracker(self,root,now=NOW):
        return GenerationFourBidAskTracker(root,now_provider=lambda:now)
    def test_population_is_mechanisms_not_parameter_grid(self):
        self.assertEqual(len(g4.ALL_IDS),36)
        self.assertEqual(len({s.mechanism for s in g4.CATALOG}),12)
        for s in g4.CATALOG:
            self.assertFalse(g4.metadata(s.strategy_id)['config']['live_order_placement'])
            self.assertEqual(s.equity,5000)
            self.assertEqual(s.notional,1000)
        self.assertFalse(g4.IDS)
    def test_registry_opt_in_and_existing_population_unchanged(self):
        code="from strategies import registry as r,generation_four as g; print(len(r.MINUTE_STRATEGIES),sum(s.name in g.ALL_IDS for s in r.MINUTE_STRATEGIES),len(r.FAILED_STRATEGIES))"
        counts=[]
        for flag in ['0','1']:
            r=subprocess.run([sys.executable,'-c',code],env={**os.environ,'ENABLE_G3_PAPER':'1','ENABLE_G4_PAPER':flag},capture_output=True,text=True,check=True)
            counts.append(list(map(int,r.stdout.strip().splitlines()[-1].split())))
        self.assertEqual(counts[1][0]-counts[0][0],36)
        self.assertEqual(counts[0][1:], [0,0]); self.assertEqual(counts[1][1:],[36,0])
    def test_actual_runner_routes_only_live_opt_in(self):
        path=Path(__file__).resolve().parents[1]/'live_strategy_runner.py'
        fn=next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
        env=dict(RUN_MODE='LIVE',G4_ENABLED=True,GENERATION_FOUR_IDS=g4.ALL_IDS,
                 GENERATION_THREE_IDS=frozenset(),GENERATION_TWO_IDS=frozenset(),GENERATION_ONE_IDS=frozenset(),
                 generation_four_outcomes=Mock(),independent_ba_outcomes=Mock(),paper_outcomes=Mock(),
                 independent_l1=Mock(),quote_source=Mock())
        env['independent_l1'].quotes.return_value={'QQQ':book()};env['quote_source'].now.return_value=NOW
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
        env['register_single_leg_paper'](signal())
        env['generation_four_outcomes'].register_signal.assert_called_once()
        for mode,flag in [('LIVE',False),('REPLAY',True)]:
            env.update(RUN_MODE=mode,G4_ENABLED=flag)
            self.assertFalse(env['register_single_leg_paper'](signal()))
        self.assertEqual(env['generation_four_outcomes'].register_signal.call_count,1)
        env['independent_ba_outcomes'].register_signal.assert_not_called()
        env['paper_outcomes'].register.assert_not_called()
    def test_no_current_return_fit_leakage(self):
        s=g4.spec_for(SID);b=[100.];p=[100.]
        for i in range(65):
            x=.08*math.sin(i*.7)+.03*math.cos(i*.3)
            b.append(b[-1]*math.exp(x/100));p.append(p[-1]*math.exp((1.3*x+.015*math.sin(i*1.7))/100))
        h={x:p.copy() for x in s.universe};h[s.benchmark]=b
        a=g4.feature_rows(s,h)[s.universe[0]]
        h[s.universe[0]][-1]*=1.03
        z=g4.feature_rows(s,h)[s.universe[0]]
        self.assertAlmostEqual(a['beta'],1.3,delta=.1)
        self.assertEqual(a['beta'],z['beta']);self.assertEqual(a['alpha'],z['alpha'])
        self.assertNotEqual(a['z'],z['z'])
    def test_all_mechanisms_have_positive_fixtures(self):
        # Fixtures isolate each distinct mathematical predicate. Extraction and
        # streaming continuity are tested separately, including no fit leakage.
        base=dict(p=[100.]*66,r=[.01]*65,br=[.01]*65,beta=1.,alpha=0.,residual=[0.]*65,
                  residual_sd=.02,ret5=.2,ret1=.04,factor5=.1,residual5=-.2,z=-3.,
                  prior_corr=.8,recent_corr=.8,disrupted_corr=0.,train_scale=.03)
        for mechanism in g4.HYPOTHESES:
            s=g4.spec_for('G4'+mechanism+'INDEX');f={**base,'p':base['p'].copy(),'r':base['r'].copy()}
            if mechanism=='RCONT':f.update(z=3.,residual5=.2)
            elif mechanism=='FAIL':f['p'][-2:]=[99.8,100.1]
            elif mechanism=='RETEST':f['p'][-6:]=[100.2,100.05,100.08,100.1,100.08,100.15]
            elif mechanism=='JCONT':f['r'][-5:]=[.005,.005,.3,.03,.03]
            elif mechanism=='JFADE':f['r'][-5:]=[.005,.005,-.3,.03,.03]
            elif mechanism=='SEMIFLIP':f['r'][-20:]=[-.04]*15+[.04]*5
            elif mechanism=='DISPCOMP':f['r'][-10:-5]=[-.2]*5;f.update(ret5=.01)
            elif mechanism=='SERIAL':
                f['r'][:30]=[.04*(-1)**i for i in range(30)]
                f['r'][-16:]=[i*.01 for i in range(16)]
            elif mechanism=='OCCUPY':f['p'][-20:-1]=[99.8]*19;f['p'][-1]=100.1
            elif mechanism=='VRSHIFT':
                f['r'][:30]=[.04*(-1)**i for i in range(30)]
                f['r'][-30:]=[-.04]*15+[.04]*15
            rows={x:{**base,'p':base['p'].copy(),'r':base['r'].copy(),'ret5':.12} for x in s.universe}
            rows[s.universe[0]]=f
            with patch.object(g4,'feature_rows',return_value=rows):
                self.assertIsNotNone(g4.predicate(s,{}),mechanism)
                rows.pop(s.universe[-1])
                self.assertIsNone(g4.predicate(s,{}),mechanism+' missing cohort')
    def test_gaps_invalid_prices_duplicate_and_overnight(self):
        s=g4.MinuteStrategy(SID);pool=(s.spec.benchmark,)+s.spec.universe
        start=NOW-timedelta(minutes=65)
        for i in range(66):s.on_snapshot(snap(start+timedelta(minutes=i),{x:100+i*.001 for x in pool}))
        self.assertEqual(s.nearest_miss['contiguous_minutes'],66)
        s.on_snapshot(snap(NOW,{x:100 for x in pool}));self.assertEqual(len(s._history['QQQ']),66)
        s.on_snapshot(snap(NOW+timedelta(minutes=2),{x:100 for x in pool}));self.assertEqual(len(s._history['QQQ']),1)
        s.on_snapshot(snap(NOW+timedelta(minutes=3),{x:float('nan') if x=='QQQ' else 100 for x in pool}))
        self.assertEqual(len(s._history['QQQ']),0)
        s.on_snapshot(snap(NOW+timedelta(days=1),{x:100 for x in pool}));self.assertEqual(len(s._history['SPY']),1)
        self.assertEqual(s.on_snapshot(snap(NOW+timedelta(days=1,seconds=1),{x:100 for x in pool})),[])
    def test_execution_anchor_partial_fills_cash_recovery_and_cooldown(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);q=book(ask=100.05,bid=100.,size=3)
            self.assertTrue(t.register_signal(signal(),q,NOW))
            r=t.active['a'];self.assertEqual(r['filled_qty'],3)
            self.assertAlmostEqual(r['target_price'],100.05*1.006)
            self.assertAlmostEqual(r['stop_price'],100.05*.996)
            self.assertIn('admission_evidence',r)
            t=self.tracker(root)
            self.assertEqual(t.active['a']['remaining_qty'],3)
            self.assertFalse(t.register_signal(signal(setup='b'),q,NOW))
            later=NOW+timedelta(seconds=20)
            self.assertEqual(t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01,size=1)},later),[])
            self.assertEqual(t.active['a']['remaining_qty'],2)
            t=self.tracker(root,now=later)
            self.assertEqual(t.active['a']['remaining_qty'],2)
            later+=timedelta(seconds=1)
            self.assertEqual(len(t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01,size=2)},later)),1)
            rows,_=calculate_generation_four(Path(root),'2026-10-08',later,{},lambda *a:{})
            self.assertAlmostEqual(rows[SID+'BA']['pnl'],3*(101.-100.05))
    def test_stale_books_contract_provenance_births_and_disabled_drain(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            cases=[{'paper_only':False},{'population_hash':'wrong'},{'completed_minute':None},{'symbol':'XYZ'},{'admission_evidence':{}},{'constituent_votes':['G3']}]
            for i,change in enumerate(cases):
                r=signal(setup=str(i));r.update(change);self.assertFalse(t.register_signal(r,book(),NOW))
            self.assertFalse(t.register_signal(signal(setup='stale'),book(NOW-timedelta(seconds=6)),NOW))
            self.assertFalse(t.register_signal(signal(now=NOW-timedelta(minutes=1),setup='past'),book(),NOW))
            self.assertTrue(t.register_signal(signal(setup='good'),book(),NOW))
            birth=t.births.copy();t=self.tracker(root,now=NOW+timedelta(days=1));self.assertEqual(t.births,birth)
            with patch('generation_one_paper_tracker.output_enabled',return_value=False):
                self.assertFalse(t.register_signal(signal(setup='disabled'),book(),NOW))
                later=NOW+timedelta(minutes=20)
                self.assertEqual(len(t.update_quotes({'QQQ':book(later)},later)),1)
                self.assertFalse(t.active)
    def test_persistent_worker_reconstructs_g4_classes_and_preserves_order(self):
        from strategies import registry
        ids=sorted(g4.ALL_IDS)
        specs=[(sid,'generation_four',sid+'Strategy') for sid in ids]
        ctx=__import__('multiprocessing').get_context('fork')
        parent,child=ctx.Pipe();process=ctx.Process(target=registry._minute_worker,args=(child,specs))
        process.start();child.close()
        try:
            parent.send((1,snap(NOW,{x:100 for s in g4.CATALOG for x in (s.benchmark,)+s.universe})))
            self.assertTrue(parent.poll(10))
            seq,rows=parent.recv()
            self.assertEqual(seq,1);self.assertEqual([r['strategy_id'] for r in rows],ids)
            self.assertTrue(all(r['error'] is None for r in rows))
            self.assertTrue(all(r['nearest_miss']['contiguous_minutes']==1 for r in rows))
        finally:
            parent.send(None);parent.close();process.join(5)
            if process.is_alive():process.terminate();process.join()
        self.assertEqual(process.exitcode,0)

    def test_frozen_manifest_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            self.assertTrue(t.register_signal(signal(),book(),NOW))
            manifest=json.loads(t.manifest_path.read_text())
            manifest['rule_source_sha256']='changed'
            t.manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):self.tracker(root)

    def test_max_hold_waits_for_fresh_quote_and_closes_at_bid(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            later=NOW+timedelta(minutes=20)
            self.assertFalse(t.update_quotes({'QQQ':book()},later));self.assertIn('a',t.active)
            closed=t.update_quotes({'QQQ':book(later,bid=99.8,ask=99.81)},later)
            self.assertEqual(closed[0]['exit_reason'],'G4_MAX_HOLD');self.assertEqual(closed[0]['exit_price'],99.8)
    def test_observed_coverage_excludes_warmup_and_errors(self):
        with tempfile.TemporaryDirectory() as root:
            start=NOW-timedelta(minutes=66);t=self.tracker(root,now=start)
            pool={x for s in g4.CATALOG for x in (s.benchmark,)+s.universe}
            for i in range(67):
                at=start+timedelta(minutes=i);t.observe_snapshot(snap(at,{x:100 for x in pool}),current=i>=65,errors=[(SID,'test')] if i==66 else [])
            row=t.observations[SID]['2026-10-08']
            self.assertEqual(row['evaluated_minutes'],2);self.assertEqual(row['ready_minutes'],1);self.assertEqual(row['error_minutes'],1)
            t.observe_snapshot(snap(NOW,{x:100 for x in pool}),current=True)
            self.assertEqual(row['evaluated_minutes'],2)
            report=build(Path(root),'2026-10-09')
            self.assertEqual(report['age_review'][0]['status'],'INSUFFICIENT_EVIDENCE')
    def test_evidence_report_does_not_use_later_exit_information(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            later=NOW+timedelta(days=1)
            t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01)},later)
            report=build(Path(root),'2026-10-09')
            # A later exit cannot retroactively count as a closed trade as of
            # midnight before that exit. The residual excludes the old session.
            self.assertEqual(report['evidence'][SID]['sessions'],[])
            path=Path(root)/(FILE_STEM+'_observations.json')
            path.write_text(json.dumps({SID:{'2026-10-08':dict(ready_minutes=310,error_minutes=0,evaluated_minutes=310)}}))
            report=build(Path(root),'2026-10-09')
            self.assertEqual(report['evidence'][SID]['sessions'][0]['closed_trades'],0)
            self.assertEqual(report['evidence'][SID]['sessions'][0]['residual_positions'],1)
            with t.ledger_path.open('a') as handle:handle.write('{bad json\n')
            report=build(Path(root),'2026-10-09')
            self.assertFalse(report['evidence'][SID]['sessions'][0]['coverage_verified'])

    def test_age_protects_new_unknown_inactive_and_malformed(self):
        sessions=[dict(day=(NOW.date()-timedelta(days=70-i)).isoformat(),return_pct=-.1,closed_trades=5,coverage_verified=True) for i in range(60)]
        evidence={'young':dict(birth_date='2026-10-07',sessions=sessions),'unknown':dict(sessions=sessions),
                  'old':dict(birth_date='2026-01-01',sessions=sessions),
                  'inactive':dict(birth_date='2026-01-01',sessions=[{**r,'closed_trades':0} for r in sessions]),
                  'protected':dict(birth_date='2026-01-01',sessions=sessions),
                  'duplicate':dict(birth_date='2026-01-01',sessions=sessions+sessions[:1])}
        rows={r['strategy_id']:r for r in review(evidence,'2026-10-08',protected={'protected'})}
        self.assertEqual(rows['old']['status'],'NEGATIVE_REVIEW_CANDIDATE')
        for sid in ['young','unknown','inactive','duplicate']:self.assertEqual(rows[sid]['status'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(rows['protected']['status'],'PROTECTED')
        self.assertFalse(any(r['retirement_authorized'] for r in rows.values()))

if __name__=='__main__':unittest.main()
