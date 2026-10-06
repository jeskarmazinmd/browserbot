from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from engine.events import MarketSnapshot,Quote
from generation_three_paper_tracker import GenerationThreeBidAskTracker,FILE_STEM
from strategies import generation_three as g3
from reporting.generation_three_performance import calculate_generation_three
from research_tools.g3_review.analyze import parse_table,audit_ledger,summarize

NOW=datetime(2026,10,7,16,30,tzinfo=timezone.utc)
def quote(now=NOW,bid=9.99,ask=10.01,size=1000,**kw):
    return dict(bid=bid,ask=ask,bid_size_raw=size,ask_size_raw=size,
                bid_time_ms=now.timestamp()*1000,ask_time_ms=now.timestamp()*1000,realtime=True,**kw)
def signal(sid='G3MCTL',now=NOW,setup='a'):
    e=dict(timestamp=now.isoformat(),symbol='XYZ',flash_drop_pct=1.4,
           pre_return_pct=1.,pre_r2=.7,pre30_return_std_pct=.2,target_price=10.5)
    r=g3.MODULES[sid].refresh_event_for_entry(e,10.);r['setup_id']=setup
    return r
def snapshot(now,prices):return MarketSnapshot(now,{s:Quote(p) for s,p in prices.items()},len(prices),len(prices),0.)

class G3Tests(unittest.TestCase):
    def tracker(self,root,now=NOW):return GenerationThreeBidAskTracker(root,now_provider=lambda:now)
    def test_unique_parameter_population_and_controls(self):
        self.assertEqual(len(g3.ALL_IDS),150)
        signatures=set()
        for s in g3.CATALOG:
            meta=g3.metadata(s.strategy_id)
            self.assertFalse(meta['config']['live_order_placement'])
            self.assertIn(s.comparison_id,g3.ALL_IDS)
            values=dict(meta['parameters'])
            for key in ['strategy_id','hypothesis','comparison_id']:values.pop(key)
            signatures.add(json.dumps(values,sort_keys=True))
        self.assertEqual(len(signatures),150)
    def test_default_off_and_opt_in_registry(self):
        code="from strategies import registry; from strategies import generation_three as g; print(len(g.IDS & registry.flash_strategy_configs().keys()),sum(s.name in g.MINUTE_IDS for s in registry.MINUTE_STRATEGIES))"
        import os
        for flag,want in [('0','0 0'),('1','66 84')]:
            r=subprocess.run([sys.executable,'-c',code],env={**os.environ,'ENABLE_G3_PAPER':flag},capture_output=True,text=True,check=True)
            self.assertEqual(r.stdout.strip().splitlines()[-1],want)
    def test_actual_runner_routes_g3_only_live_and_enabled(self):
        import ast
        from unittest.mock import Mock
        from strategies import generation_one,generation_two
        path=Path(__file__).resolve().parents[1]/'live_strategy_runner.py'
        fn=next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
        env=dict(RUN_MODE='LIVE',G3_ENABLED=True,GENERATION_THREE_IDS=g3.ALL_IDS,
                 GENERATION_TWO_IDS=generation_two.IDS,GENERATION_ONE_IDS=generation_one.IDS,
                 generation_three_outcomes=Mock(),generation_two_outcomes=Mock(),generation_one_outcomes=Mock(),
                 independent_ba_outcomes=Mock(),paper_outcomes=Mock(),independent_l1=Mock(),quote_source=Mock())
        env['independent_l1'].quotes.return_value={'XYZ':quote()};env['quote_source'].now.return_value=NOW
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
        env['register_single_leg_paper'](signal())
        env['generation_three_outcomes'].register_signal.assert_called_once()
        for mode,flag in [('REPLAY',True),('LIVE',False)]:
            env.update(RUN_MODE=mode,G3_ENABLED=flag)
            self.assertFalse(env['register_single_leg_paper'](signal()))
        self.assertEqual(env['generation_three_outcomes'].register_signal.call_count,1)
        env['independent_ba_outcomes'].register_signal.assert_not_called()
    def test_retirement_protected_sources_and_drain(self):
        from strategies.research_retirement import _read_plan
        from strategies.output_switches import output_enabled
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'plan.json'
            path.write_text(json.dumps({'schema':'G3_RETIREMENT_V1','entry_and_evaluation_ids':['PMID']}))
            with self.assertRaises(ValueError):_read_plan(str(path))
            path.write_text(json.dumps({'schema':'G3_RETIREMENT_V1','entry_and_evaluation_ids':['G3MCTL']}))
            t=self.tracker(root);self.assertTrue(t.register_signal(signal(),quote(),NOW))
            with patch.dict('os.environ',{'G3_RETIREMENT_PLAN_PATH':str(path)}):
                self.assertFalse(output_enabled('G3MCTLBA'))
                self.assertFalse(t.register_signal(signal(setup='b'),quote(),NOW))
                later=NOW+timedelta(seconds=10)
                self.assertEqual(len(t.update_quotes({'XYZ':quote(later,bid=10.6,ask=10.61)},later)),1)
    def test_flash_no_source_output_dependency(self):
        with patch('strategies.strategy_pmid.accepts_flash',side_effect=AssertionError()):
            self.assertTrue(g3.MODULES['G3MCTL'].accepts_flash(dict(flash_drop_pct=1.4,pre_return_pct=1,pre_r2=.7),12))
    def test_midday_and_weekend_boundaries(self):
        s=g3.spec_for('G3MCTL')
        self.assertFalse(g3.time_admits(s,NOW.replace(hour=15,minute=59)))
        self.assertTrue(g3.time_admits(s,NOW.replace(hour=16,minute=0)))
        self.assertFalse(g3.time_admits(s,NOW.replace(hour=18,minute=0)))
        self.assertFalse(g3.time_admits(s,NOW.replace(day=10)))
    def test_bad_numbers_fail_closed(self):
        for value in ['NaN',float('inf'),None]:
            self.assertFalse(g3.raw_accepts(g3.spec_for('G3MCTL'),dict(flash_drop_pct=1.4,pre_return_pct=value,pre_r2=.8),12))
    def test_actual_ask_geometry_and_paper_only_files(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);self.assertTrue(t.register_signal(signal(),quote(ask=10.1,bid=10.09),NOW))
            row=t.active['a'];self.assertAlmostEqual(row['stop_price'],10.1*.95)
            self.assertEqual(row['entry_price'],10.1)
            self.assertFalse(any(p.name.startswith('paper_signal') for p in Path(root).iterdir()))
    def test_stale_bid_blocks_admission(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);q=quote();q['bid_time_ms']-=6000
            self.assertFalse(t.register_signal(signal(),q,NOW))
    def test_future_ask_blocks_admission(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);q=quote();q['ask_time_ms']+=1001
            self.assertFalse(t.register_signal(signal(),q,NOW))
    def test_spread_and_final_target_gates(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            self.assertFalse(t.register_signal(signal('G3MS5'),quote(),NOW))
            self.assertFalse(t.register_signal(signal('G3MU150',setup='b'),quote(ask=10.4,bid=10.39),NOW))
    def test_duplicate_book_cannot_fill_twice(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);q=quote(size=10)
            self.assertTrue(t.register_signal(signal(setup='a'),q,NOW))
            self.assertFalse(t.register_signal(signal(setup='b'),q,NOW))
            recovered=self.tracker(root)
            self.assertFalse(recovered.register_signal(signal(setup='c'),q,NOW))
    def test_partial_exit_restart_actual_quantities(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);self.assertTrue(t.register_signal(signal(),quote(size=20),NOW))
            t.update_quotes({'XYZ':quote(NOW+timedelta(seconds=10),bid=10.6,ask=10.61,size=7)},NOW+timedelta(seconds=10))
            self.assertEqual(t.active['a']['remaining_qty'],13)
            r=self.tracker(root);self.assertEqual(r.active['a']['remaining_qty'],13)
            closed=r.update_quotes({'XYZ':quote(NOW+timedelta(seconds=20),bid=10.6,ask=10.61,size=100)},NOW+timedelta(seconds=20))
            self.assertEqual(len(closed),1);self.assertAlmostEqual(closed[0]['pnl'],20*(10.6-10.01))
    def test_checkpoint_clock_begins_at_fill(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root,NOW-timedelta(seconds=100));s=signal('G3MK5',now=NOW-timedelta(seconds=100))
            self.assertTrue(t.register_signal(s,quote(),NOW))
            t.update_quotes({'XYZ':quote(NOW+timedelta(seconds=250))},NOW+timedelta(seconds=250))
            self.assertIn('a',t.active)
            t.update_quotes({'XYZ':quote(NOW+timedelta(seconds=301))},NOW+timedelta(seconds=301))
            self.assertNotIn('a',t.active)
    def test_cooldown_remembers_completed_fill_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);s=signal('G3MCD10');self.assertTrue(t.register_signal(s,quote(),NOW))
            later=NOW+timedelta(seconds=10);t.update_quotes({'XYZ':quote(later,bid=10.6,ask=10.61)},later)
            r=self.tracker(root)
            self.assertFalse(r.register_signal(signal('G3MCD10',now=later,setup='b'),quote(later),later))
            later=NOW+timedelta(seconds=601)
            self.assertTrue(r.register_signal(signal('G3MCD10',now=later,setup='c'),quote(later),later))
    def test_symbol_guard_includes_residual(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);self.assertTrue(t.register_signal(signal('G3MONE'),quote(size=20),NOW))
            later=NOW+timedelta(seconds=10);t.update_quotes({'XYZ':quote(later,bid=10.6,ask=10.61,size=7)},later)
            self.assertFalse(t.register_signal(signal('G3MONE',now=later,setup='b'),quote(later),later))
    def test_quote_rotation_does_not_starve_symbols(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            for i in range(501):t.by_symbol[str(i)]={'a'}
            first=t.symbols();second=t.symbols()
            self.assertEqual(len(first),400);self.assertEqual(len(first|second),501)
    def test_birth_and_replay_age(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            self.assertFalse(t.register_signal(signal(now=NOW-timedelta(seconds=1)),quote(),NOW))
            births=dict(t.births);self.assertEqual(self.tracker(root).births,births)
    def test_risk_and_total_cash_limits(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            self.assertTrue(t.register_signal(signal('G3MR10'),quote(),NOW))
            self.assertLessEqual(t.active['a']['filled_qty']*10.01*.05,5.)
            for i in range(7):
                now=NOW+timedelta(seconds=i+1)
                t.register_signal(signal(now=now,setup='x'+str(i)),quote(now),now)
            self.assertGreaterEqual(t._cash_for('G3MCTL',NOW)[1],0.)
    def test_minute_gap_missing_duplicate_out_of_order(self):
        t=g3.MinuteStrategy('G3TCTL')
        for i in range(31):t.on_snapshot(snapshot(NOW+timedelta(minutes=i),{'SPY':100+i*.1}))
        self.assertEqual(len(t._history['SPY']),31)
        self.assertEqual(t.on_snapshot(snapshot(NOW+timedelta(minutes=30),{'SPY':200})),[])
        self.assertEqual(len(t._history['SPY']),31)
        t.on_snapshot(snapshot(NOW+timedelta(minutes=32),{'SPY':104}))
        self.assertEqual(len(t._history['SPY']),1)
        t.on_snapshot(snapshot(NOW+timedelta(minutes=33),{}))
        self.assertEqual(len(t._history['SPY']),0)
    def test_new_session_resets_history(self):
        t=g3.MinuteStrategy('G3TCTL');t.on_snapshot(snapshot(NOW,{'SPY':100}))
        t.on_snapshot(snapshot(NOW+timedelta(days=1),{'SPY':110}))
        self.assertEqual(len(t._history['SPY']),1)
    def test_no_intraminute_history(self):
        t=g3.MinuteStrategy('G3TCTL');t.on_snapshot(snapshot(NOW+timedelta(seconds=1),{'SPY':100}))
        self.assertFalse(t._history)
    def test_minute_synthetic_source_parity_on_contiguous_data(self):
        from strategies.strategy_trendx2 import Strategy
        source=Strategy();child=g3.MinuteStrategy('G3TCTL')
        for i in range(32):
            s=snapshot(NOW+timedelta(minutes=i),{'SPY':100+i*.1})
            a,b=source.on_snapshot(s),child.on_snapshot(s)
            self.assertEqual(bool(a),bool(b))
            if a:self.assertEqual(a[0].symbol,b[0].symbol)
    def test_rotation_breadth_gas_predicates(self):
        h={s:[100+i*.03 for i in range(31)] for s in g3.COMMODITIES}
        self.assertIsNotNone(g3.minute_predicate(g3.spec_for('G3CCTL'),h))
        self.assertIsNotNone(g3.minute_predicate(g3.spec_for('G3CBCTL'),h))
        gas={'UNG':[100+i*.05 for i in range(16)],'XLE':[100+i*.01 for i in range(16)]}
        self.assertEqual(g3.minute_predicate(g3.spec_for('G3CGCTL'),gas)[1],'UNG')
        gas['XLE']=[100]*16
        self.assertIsNone(g3.minute_predicate(g3.spec_for('G3CGCTL'),gas))
    def test_minute_execution_rejects_missing_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root)
            s=dict(timestamp=NOW.isoformat(),symbol='XYZ',strategy_id='G3TCTL',entry_price=10,target_price=10.5,stop_price=9.9,constituent_votes=['TRENDX2'])
            self.assertFalse(t.register_signal(s,quote(),NOW))
    def test_reporting_uses_actual_partial_fills(self):
        with tempfile.TemporaryDirectory() as root:
            t=self.tracker(root);t.register_signal(signal(),quote(size=7),NOW)
            later=NOW+timedelta(seconds=10);t.update_quotes({'XYZ':quote(later,bid=10.6,ask=10.61)},later)
            modules,_=calculate_generation_three(Path(root),'2026-10-07',later,{},lambda *a:{})
            self.assertAlmostEqual(modules['G3MCTLBA']['pnl'],7*(10.6-10.01))
    def test_audit_missing_returns_and_cumulative_exit_not_doubled(self):
        _,rows=parse_table('Module 10-01 10-02 SUM\n1 PMIDBA +1.00% - +1.00%')
        self.assertIsNone(rows['PMIDBA']['10-02'])
        self.assertEqual(summarize([1,None])['observed_sessions'],1)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'ledger.jsonl'
            e=dict(strategy_id='X',setup_id='a',symbol='ABC',entry_price=10,filled_qty=10,notional=100)
            records=[dict(e,event_type='PAPER_ENTRY'),dict(e,event_type='PAPER_PARTIAL_EXIT',realized_proceeds=44,exit_fill_qty=4,pnl=4),dict(e,event_type='PAPER_EXIT',realized_proceeds=110,exit_fill_qty=6,pnl=10)]
            p.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            trades,summary,_,_=audit_ledger(p)
            self.assertEqual(summary[0]['closed_pnl'],10)
            self.assertFalse(trades[0]['exit_quantity_mismatch'])

if __name__=='__main__':unittest.main()
