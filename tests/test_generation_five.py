import ast
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
from engine.events import MarketSnapshot,Quote
from strategies import generation_five as g
from generation_five_paper_tracker import GenerationFiveBidAskTracker,FILE_STEM
from reporting.generation_five_performance import calculate_generation_five

NOW=datetime(2026,10,8,16,0,tzinfo=timezone.utc)
SID='G5TRCTL'
def book(now=NOW,bid=99.99,ask=100.,size=1000):
    return dict(bid=bid,ask=ask,bid_size_raw=size,ask_size_raw=size,
                bid_time_ms=now.timestamp()*1000,ask_time_ms=now.timestamp()*1000,realtime=True)
def signal(sid=SID,now=NOW,symbol='QQQ'):
    s=g.spec_for(sid)
    votes={'RB':['LEADERSHIP','BREADTH'],'SECTOR':['STOCK_TREND','SECTOR_TREND'],
           'BREAK':['TREND','BREAKOUT']}.get(s.mechanism,[s.mechanism])
    row = dict(strategy_id=sid,symbol=symbol,timestamp=now.isoformat(),
                completed_minute=now.isoformat(),entry_price=100.,target_price=100.9,stop_price=99.35,
                paper_only=True,live_order_placement=False,rule_version=g.RULE_VERSION,
                population_hash=g.POPULATION_HASH,rule_source_sha256=g.RULE_SOURCE_SHA256,
                admission_evidence={'lagged_std_pct':.1,'ret30':1.5},constituent_votes=votes)
    if s.checkpoint_seconds:row.update(exit_model='k_checkpoint',mode='conditional_return',seconds=s.checkpoint_seconds,min_return_pct=0.)
    return row
def tracker(root):return GenerationFiveBidAskTracker(root,now_provider=lambda:NOW)
class Tests(unittest.TestCase):
    def test_all_admissions_and_agreement_are_explicit(self):
        from unittest.mock import patch
        base=dict(price=100.,ret30=1.3,ret15=.6,ret5=.3,ret1=.1,up_fraction=.7,
                  prior_range_pct=1.2,breakout_pct=.2,lagged_std_pct=.2,
                  flash_drop_pct=1.2,rebound_pct=.2,pre_return_pct=1.,pre_r2=.6,
                  pre_std_pct=.2,volatility_units=6.)
        for mechanism in g.HYPOTHESES:
            spec=g.spec_for('G5'+mechanism+'CTL')
            needed=set(spec.universe)|{'SPY'}|set(g.PROXIES.values())
            history={sym:dict(base) for sym in needed}
            if mechanism=='PULL':
                for f in history.values():f['ret5']=-.2
            with patch.object(g,'features',side_effect=lambda prices:prices):
                candidate=g.candidate(spec,history)
                self.assertIsNotNone(candidate,mechanism)
                self.assertEqual(len(candidate[-1]),spec.votes)
        spec=g.spec_for('G5SECTORCTL')
        history={sym:dict(base) for sym in set(spec.universe)|set(g.PROXIES.values())|{'SPY'}}
        for sym in g.PROXIES.values():history[sym]['ret30']=0.
        with patch.object(g,'features',side_effect=lambda prices:prices):
            self.assertIsNone(g.candidate(spec,history))
    def test_pretrend_fit_and_shock_scale_do_not_use_current_price(self):
        p=[100.]
        for i in range(34):p.append(p[-1]*(1+(.2 if i%2 else -.1)/100))
        a=g.features(p);p[-1]*=1.05;b=g.features(p)
        self.assertEqual(a['pre_std_pct'],b['pre_std_pct'])
        self.assertEqual(a['pre_r2'],b['pre_r2'])
        self.assertEqual(a['lagged_std_pct'],b['lagged_std_pct'])
    def test_corrupt_recovery_does_not_invent_performance(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            with Path(root,FILE_STEM+'_outcomes.jsonl').open('a') as f:f.write('{broken\n')
            with self.assertRaises(ValueError):tracker(root)
    def test_registry_opt_in_and_old_generations_intact(self):
        code="from strategies import registry as r,generation_one as a,generation_one_minute as b,generation_two as c,generation_three as d,generation_four as e,generation_five as f; print(len(r.MINUTE_STRATEGIES),sum(x.name in d.MINUTE_IDS for x in r.MINUTE_STRATEGIES),sum(x.name in e.MINUTE_IDS for x in r.MINUTE_STRATEGIES),sum(x.name in f.MINUTE_IDS for x in r.MINUTE_STRATEGIES),len(r.FAILED_STRATEGIES),len(a.IDS|b.IDS),len(c.IDS))"
        counts=[]
        for flag in ('0','1'):
            p=subprocess.run([sys.executable,'-c',code],env={**os.environ,'ENABLE_G3_PAPER':'1','ENABLE_G4_PAPER':'1','ENABLE_G5_PAPER':flag},capture_output=True,text=True,check=True)
            counts.append(list(map(int,p.stdout.strip().splitlines()[-1].split())))
        self.assertEqual(counts[1][0]-counts[0][0],96)
        self.assertEqual(counts[1][1:5],[84,36,96,0])
        self.assertEqual(counts[0][1:3],counts[1][1:3]);self.assertEqual(counts[0][5:],counts[1][5:])
        self.assertEqual(len(g.CATALOG),len(g.ALL_IDS));self.assertEqual(len(g.HYPOTHESES),12)
    def test_runner_routes_only_live_opt_in(self):
        path=Path('live_strategy_runner.py');fn=next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
        env=dict(RUN_MODE='LIVE',G5_ENABLED=True,GENERATION_FIVE_IDS=g.ALL_IDS,
                 GENERATION_ONE_IDS=set(),GENERATION_TWO_IDS=set(),GENERATION_THREE_IDS=set(),GENERATION_FOUR_IDS=set(),
                 generation_five_outcomes=Mock(),independent_ba_outcomes=Mock(),paper_outcomes=Mock(),independent_l1=Mock(),quote_source=Mock())
        env['independent_l1'].quotes.return_value={'QQQ':book()};env['quote_source'].now.return_value=NOW
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
        env['register_single_leg_paper'](signal());env['generation_five_outcomes'].register_signal.assert_called_once()
        for mode,flag in [('LIVE',False),('REPLAY',True)]:
            env.update(RUN_MODE=mode,G5_ENABLED=flag);self.assertFalse(env['register_single_leg_paper'](signal()))
        self.assertEqual(env['generation_five_outcomes'].register_signal.call_count,1)
        env['independent_ba_outcomes'].register_signal.assert_not_called()
    def test_prospective_birth_restart_and_no_backfill(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);births=t.births.copy()
            self.assertFalse(t.register_signal(signal(now=NOW-timedelta(minutes=1)),book(),NOW))
            self.assertFalse(t.register_signal(signal(now=NOW+timedelta(minutes=1)),book(),NOW))
            self.assertTrue(t.register_signal(signal(),book(),NOW))
            self.assertEqual(tracker(root).births,births)
            Path(root,FILE_STEM+'_births.json').unlink()
            with self.assertRaises(ValueError):tracker(root)
    def test_entry_liquidity_and_capital(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root)
            self.assertTrue(t.register_signal(signal(),book(size=3),NOW))
            row=next(iter(t.active.values()));self.assertEqual(row['filled_qty'],3);self.assertEqual(row['entry_price'],100.)
            self.assertEqual(row['notional'],300.)
            self.assertAlmostEqual(t._cash_for(SID,NOW)[1],4700)
            self.assertFalse(t.register_signal(signal(),book(size=3),NOW))
    def test_no_future_stale_or_midpoint_admission(self):
        for age in (-1,6000):
            with tempfile.TemporaryDirectory() as root:
                t=tracker(root);q=book();q['ask_time_ms']=NOW.timestamp()*1000-age
                self.assertFalse(t.register_signal(signal(),q,NOW))
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);s=signal();s['entry_price']=99.995
            self.assertTrue(t.register_signal(s,book(),NOW));self.assertEqual(next(iter(t.active.values()))['entry_price'],100)
    def test_shared_exit_book_partial_recovery_and_reporting(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            later=NOW+timedelta(minutes=5)
            self.assertTrue(t.register_signal(signal(now=later),book(later),later))
            exit_time=later+timedelta(minutes=1);q=book(exit_time,bid=101.,ask=101.01,size=12)
            closed=t.update_quotes({'QQQ':q},exit_time)
            self.assertEqual(len(closed),1);self.assertEqual(sum(r['remaining_qty'] for r in t.active.values()),8)
            # Same quote cannot be spent again after restart.
            t=tracker(root);self.assertFalse(t.update_quotes({'QQQ':q},exit_time))
            later=exit_time+timedelta(seconds=1)
            self.assertEqual(len(t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01,size=100)},later)),1)
            report,_=calculate_generation_five(Path(root),'2026-10-08',later,{},lambda s,m:book(later))
            self.assertAlmostEqual(report[SID+'BA']['pnl'],20.)
            self.assertTrue(report[SID+'BA']['actual_fill_quantities'])
    def test_exec_conservative_participation_and_exit_freshness(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TREXEC';self.assertTrue(t.register_signal(signal(sid),book(size=30),NOW))
            self.assertEqual(next(iter(t.active.values()))['filled_qty'],3)
            later=NOW+timedelta(seconds=2)
            self.assertFalse(t.update_quotes({'QQQ':book(NOW,bid=101,ask=101.01)},later))
            self.assertEqual(len(t.update_quotes({'QQQ':book(later,bid=101,ask=101.01)},later)),1)
    def test_time_exit_and_symbol_concentration(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TRTIME';self.assertTrue(t.register_signal(signal(sid),book(),NOW))
            later=NOW+timedelta(minutes=15)
            closed=t.update_quotes({'QQQ':book(later)},later);self.assertEqual(closed[0]['exit_reason'],'G5_MAX_HOLD')
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TRDIVER';self.assertTrue(t.register_signal(signal(sid),book(),NOW))
            later=NOW+timedelta(minutes=11)
            self.assertFalse(t.register_signal(signal(sid,later),book(later),later))
    def test_contiguous_minute_history_and_no_cross_session_leak(self):
        s=g.MinuteStrategy('G5ROTCTL');start=NOW-timedelta(minutes=34)
        for i in range(35):
            t=start+timedelta(minutes=i);prices={x:Quote(100*(1.001**i)) for x in g.COMMODITIES}
            result=s.on_snapshot(MarketSnapshot(t,prices,len(prices),len(prices),0))
        self.assertTrue(result)
        gap=NOW+timedelta(minutes=2)
        self.assertFalse(s.on_snapshot(MarketSnapshot(gap,prices,len(prices),len(prices),0)))
        self.assertFalse(s.on_snapshot(MarketSnapshot(gap,prices,len(prices),len(prices),0)))
    def test_progress_clock_volatility_risk_and_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TRPROG';self.assertTrue(t.register_signal(signal(sid),book(),NOW))
            later=NOW+timedelta(minutes=10)
            closed=t.update_quotes({'QQQ':book(later)},later)
            self.assertEqual(closed[0]['exit_reason'],'CONDITIONAL_RETURN_600S')
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TRVOL';self.assertTrue(t.register_signal(signal(sid),book(),NOW))
            r=next(iter(t.active.values()));self.assertLess(r['stop_price'],r['entry_price'])
            self.assertGreater(r['target_price'],r['entry_price'])
            entry=json.loads(Path(root,FILE_STEM+'_outcomes.jsonl').read_text().splitlines()[0])
            self.assertIn('execution_evidence',entry)
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);sid='G5TRRISK';self.assertTrue(t.register_signal(signal(sid),book(ask=1000.,bid=999.9),NOW))
            self.assertLessEqual(next(iter(t.active.values()))['notional'],1000.)
            p=Path(root,FILE_STEM+'_manifest.json');p.write_text('{}')
            with self.assertRaises(ValueError):tracker(root)
    def test_reports_require_fresh_open_marks_and_expose_carries(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            later=NOW+timedelta(minutes=1)
            rows,diag=calculate_generation_five(Path(root),'2026-10-08',later,{},lambda s,m:book())
            self.assertNotIn(SID+'BA',rows);self.assertEqual(diag['unmarked'],1)
            rows,diag=calculate_generation_five(Path(root),'2026-10-09',later+timedelta(days=1),{},lambda s,m:book())
            self.assertNotIn(SID+'BA',rows);self.assertEqual(diag['overnight_carry_unverified_modules'],1)
    def test_prospective_evidence_report_uses_actual_proceeds(self):
        from research_tools.g5_review.report import build
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(build(root,NOW)['status'],'not_activated')
            t=tracker(root);self.assertTrue(t.register_signal(signal(),book(),NOW))
            later=NOW+timedelta(minutes=1);t.update_quotes({'QQQ':book(later,bid=101.,ask=101.01)},later)
            report=build(root,later);self.assertTrue(report['verified'])
            self.assertEqual(report['modules'][SID]['closed_fill_pnl'],10.)
            self.assertEqual(report['modules'][SID]['excluding_best_trade_pnl'],0.)
    def test_ready_coverage_warmup_not_counted(self):
        with tempfile.TemporaryDirectory() as root:
            t=tracker(root);prices={x:Quote(100.) for x in set(g.EQUITIES)|set(g.COMMODITIES)}
            for i in range(35):
                now=NOW+timedelta(minutes=i);snap=MarketSnapshot(now,prices,len(prices),len(prices),0)
                t.observe_snapshot(snap,current=False)
            self.assertEqual(t.observations,{})
            t.observe_snapshot(MarketSnapshot(now+timedelta(minutes=1),prices,len(prices),len(prices),0),current=True)
            self.assertEqual(t.observations[SID]['2026-10-08']['ready_minutes'],1)
if __name__=='__main__':unittest.main()
