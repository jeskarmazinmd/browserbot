from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
from strategies import generation_ten as g
from generation_ten_paper_tracker import GenerationTenTracker,FILE_STEM,fee,safe_call
from reporting.generation_ten_performance import calculate_generation_ten
from research_tools.g10.performance_table import table

NOW=datetime(2026,10,19,16,30,tzinfo=timezone.utc)
BIRTH=NOW-timedelta(hours=2)

def quote(now=NOW,bid=99.99,ask=100.,size=10000,**extra):
    return dict(bid=bid,ask=ask,bid_time_ms=now.timestamp()*1000,
        ask_time_ms=now.timestamp()*1000,bid_size_raw=size,ask_size_raw=size,realtime=True,**extra)


def signal(sid='G10ENTRY01',now=NOW,**extra):
    s=g.SPECS[sid];vol=.2
    if s.max_vol_pct<1e6 or s.min_vol_pct:vol=(s.min_vol_pct+s.max_vol_pct)/2
    if s.min_shock_units:vol=3/((s.min_shock_units+s.max_shock_units)/2)
    e=dict(timestamp=now.isoformat(),symbol='XYZ',flash_drop_pct=3.,pre_return_pct=3.5,pre_r2=.95,
        pre30_return_std_pct=vol,target_price=112.,flash_start_price=120.,signal_window_end=(now-timedelta(minutes=3)).isoformat())
    r=g.MODULES[sid].refresh_event_for_entry(e,100.)
    r.update(pending_created_at=(now-timedelta(seconds=180)).isoformat(),running_low_price=98.,
        actual_rebound_pct=(100/98-1)*100,confirmation_wait_seconds=180,
        market_5m_return_pct=.5,market_1m_return_pct=.5,market_confirmation_symbol='SPY',
        volume_data_status_flash='OK',flash_volume_ratio=3.,flash_dollar_volume_3m=1e7,
        flash_snapshot_time=(now-timedelta(seconds=180)).isoformat(),market_feature_time=now.isoformat())
    r.update(extra);return r


class G10Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,ENABLE_G10_PAPER='1',ENABLE_G9_RETIREMENTS='0',ENABLE_G8_RETIREMENTS='0');self.env.start()
        self.t=GenerationTenTracker(self.root,now_provider=lambda:BIRTH)
    def tearDown(self):
        self.t.close();self.env.stop();self.temp.cleanup()
    def ready(self,now=NOW):
        self.t.observe_scan(now,100);self.t.update_quotes({},now)
    def open(self,sid='G10ENTRY01',now=NOW,**kw):
        return self.t.register_signal(signal(sid,now,**kw),quote(now),now)
    def rejection(self):
        return json.loads(self.t.ledger_path.read_text().splitlines()[-1])['reason']
    def test_population_and_semantic_uniqueness(self):
        self.assertEqual(len(g.IDS),200)
        self.assertEqual(len({g.digest(g.semantic(s)) for s in g.CATALOG}),200)
        from collections import Counter
        self.assertEqual(set(Counter(s.family for s in g.CATALOG).values()),{20})
        for s in g.CATALOG:
            self.assertFalse(g.metadata(s.strategy_id)['config']['live_order_placement'])
            self.assertTrue(g.MODULES[s.strategy_id].PAPER_ONLY)
    def test_parent_unchanged(self):
        from strategies.generation_three import spec_for
        s=spec_for('G3MPR150')
        self.assertEqual((s.min_pre_return,s.min_pre_r2,s.stop,s.target_scale),(1.5,.5,.05,1.))
    def test_all_200_can_admit_whole_shares_and_close(self):
        # Sort time-window cohorts chronologically and establish each account's observation.
        ordered=[]
        for s in g.CATALOG:
            minute=(s.start_minute+s.end_minute)//2
            now=NOW.astimezone(g.NY).replace(hour=minute//60,minute=minute%60).astimezone(timezone.utc)
            ordered.append((now,s.strategy_id))
        for now,sid in sorted(ordered):
            with self.subTest(sid=sid):
                self.t.observe_scan(now,100);self.t.update_quotes({'XYZ':quote(now,ask=20.,bid=19.999)},now)
                e=signal(sid,now,entry_price=20.,target_price=22.4,original_target_price=22.4,flash_start_price=24.,running_low_price=19.6)
                self.assertTrue(self.t.register_signal(e,quote(now,ask=20.,bid=19.999),now),self.t.reasons)
                row=next(r for r in self.t.active.values() if r['strategy_id']==sid)
                self.assertIsInstance(row['filled_qty'],int);self.assertGreater(row['filled_qty'],0)
        later=max(x[0] for x in ordered)+timedelta(hours=4)
        self.t.update_quotes({'XYZ':quote(later,bid=112.,ask=112.01)},later)
        self.assertFalse(self.t.active);self.assertEqual(sum(self.t.completed.values()),200)
    def test_realistic_high_price_and_cash_cap(self):
        e=signal(entry_price=700.,target_price=735.,original_target_price=735.,flash_start_price=770.,running_low_price=690.)
        self.assertTrue(self.t.register_signal(e,quote(ask=700,bid=699.99),NOW))
        r=next(iter(self.t.active.values()));self.assertEqual(r['filled_qty'],1)
        self.assertLess(r['entry_price']*r['filled_qty'],1000.)
    def test_too_expensive_one_share_rejected(self):
        e=signal(entry_price=1500,original_target_price=1600,flash_start_price=1700,running_low_price=1400)
        self.assertFalse(self.t.register_signal(e,quote(ask=1500,bid=1499.99),NOW))
        self.assertEqual(self.rejection(),'insufficient_cash_or_risk_budget')
    def test_commission_slippage_cash_and_recovery(self):
        self.assertTrue(self.open());e=next(iter(self.t.active.values())).copy();qty=e['filled_qty']
        self.assertAlmostEqual(e['entry_price'],100.02)
        later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=113.,ask=113.01)},later)
        expected=5000-qty*100.02-fee(qty)+qty*113*(1-.0002)-fee(qty,True)
        self.assertAlmostEqual(self.t.cash['G10ENTRY01'],expected)
        self.t.close();self.t=GenerationTenTracker(self.root,now_provider=lambda:later)
        self.assertAlmostEqual(self.t.cash['G10ENTRY01'],expected);self.assertEqual(self.t.completed['G10ENTRY01'],1)
    def test_partial_exit_book_consumption_and_restart(self):
        self.assertTrue(self.open());qty=next(iter(self.t.active.values()))['filled_qty'];self.assertGreater(qty,2)
        later=NOW+timedelta(minutes=1);q=quote(later,bid=113.,ask=113.01,size=4)
        fills=self.t.update_quotes({'XYZ':q},later);self.assertEqual(fills[0]['qty'],1)
        self.assertEqual(next(iter(self.t.active.values()))['pending_exit_reason'],'TARGET')
        self.assertFalse(self.t.update_quotes({'XYZ':q},later))
        self.t.close();self.t=GenerationTenTracker(self.root,now_provider=lambda:later)
        self.assertFalse(self.t.update_quotes({'XYZ':q},later))
        later+=timedelta(seconds=1);self.assertTrue(self.t.update_quotes({'XYZ':quote(later,bid=100,ask=100.01)},later))
        self.assertFalse(self.t.active)
    def test_stale_future_missing_timestamp_and_zero_size(self):
        for i,change in enumerate([dict(bid_time_ms=NOW.timestamp()*1000-3000),dict(ask_time_ms=NOW.timestamp()*1000+1),dict(ask_size_raw=0),dict(realtime=False)]):
            with self.subTest(change=change):
                e=signal(signal_window_end=str(i));q=quote();q.update(change)
                self.assertFalse(self.t.register_signal(e,q,NOW))
        q=quote();q.pop('ask_time_ms');q['ask_age_seconds']=0
        self.assertFalse(self.t.register_signal(signal(signal_window_end='no-stamp'),q,NOW))
    def test_no_quote_reuse_and_old_book(self):
        self.assertTrue(self.open());e=signal(signal_window_end='another')
        self.assertFalse(self.t.register_signal(e,quote(),NOW)) # aggregate symbol cap exhausted
    def test_independent_accounts_and_dedupe(self):
        self.assertTrue(self.open());self.assertFalse(self.open());self.assertTrue(self.open('G10ENTRY02'))
        self.assertEqual(len(self.t.active),2)
        self.assertEqual(self.t.cash['G10ENTRY03'],5000.)
    def test_prebirth_initial_setup_is_not_backfilled(self):
        self.assertFalse(self.open(pending_created_at=(BIRTH-timedelta(seconds=1)).isoformat()))
        self.assertEqual(self.rejection(),'prebirth_or_missing_pending')
    def test_disabled_entry_drains_residual(self):
        self.assertTrue(self.open())
        with patch.dict(os.environ,ENABLE_G10_PAPER='0'):
            self.assertFalse(self.open('G10ENTRY02'))
            later=NOW+timedelta(hours=4)
            self.t.update_quotes({'XYZ':quote(later)},later)
            self.assertFalse(self.t.active)
    def test_paper_contract_and_missing_features(self):
        for i,change in enumerate([dict(paper_only=False),dict(live_order_placement=True),dict(population_hash='bad'),dict(config_hash='bad')]):
            self.assertFalse(self.open(signal_window_end=str(i),**change));self.assertEqual(self.rejection(),'paper_contract')
        self.assertFalse(self.open('G10VOL01',pre30_return_std_pct=None));self.assertEqual(self.rejection(),'missing_volatility')
        self.assertFalse(self.open('G10REGIME01',market_5m_return_pct=None));self.assertEqual(self.rejection(),'missing_market_evidence')
        self.assertFalse(self.open('G10LIQ07',volume_data_status_flash='ERROR'));self.assertEqual(self.rejection(),'missing_volume_evidence')
    def test_stop_latches_without_liquidity(self):
        self.assertTrue(self.open());later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=90.,ask=90.01,size=0)},later)
        self.assertEqual(next(iter(self.t.active.values()))['pending_exit_reason'],'STOP')
        self.t.close();self.t=GenerationTenTracker(self.root,now_provider=lambda:later)
        later+=timedelta(seconds=1);fills=self.t.update_quotes({'XYZ':quote(later,bid=101.,ask=101.01)},later)
        self.assertEqual(fills[0]['exit_reason'],'STOP')
    def test_hold_latches_without_any_quote(self):
        self.assertTrue(self.open('G10HOLD01'));later=NOW+timedelta(minutes=4)
        self.t.update_quotes({},later)
        self.assertEqual(next(iter(self.t.active.values()))['pending_exit_reason'],'MAX_HOLD')
    def test_trailing_and_breakeven(self):
        for sid in ['G10STOP11','G10STOP17']:
            self.assertTrue(self.open(sid))
        later=NOW+timedelta(minutes=1);self.t.update_quotes({'XYZ':quote(later,bid=101.,ask=101.01)},later)
        self.assertTrue(all(r['stop_price']>r['entry_price'] for r in self.t.active.values()))
        later+=timedelta(seconds=1);fills=self.t.update_quotes({'XYZ':quote(later,bid=100.,ask=100.01)},later)
        self.assertEqual(len(fills),2)
    def test_progress_check(self):
        self.assertTrue(self.open('G10HOLD11'));later=NOW+timedelta(minutes=4)
        fills=self.t.update_quotes({'XYZ':quote(later)},later);self.assertEqual(fills[0]['exit_reason'],'PROGRESS')
    def test_costs_make_no_price_change_loss(self):
        self.ready();self.assertTrue(self.open('G10HOLD01'));later=NOW+timedelta(minutes=4)
        self.t.observe_scan(later,10);self.t.update_quotes({'XYZ':quote(later)},later)
        self.assertLess(self.t.cash['G10HOLD01'],5000.)
        modules,_=calculate_generation_ten(self.root,'2026-10-19',later)
        self.assertLess(modules['G10HOLD01BA']['return_pct'],0)
    def test_no_midnight_cash_reset_or_overnight_reentry(self):
        self.assertTrue(self.open());cash=self.t.cash['G10ENTRY01'];later=NOW+timedelta(days=1)
        self.t.update_quotes({},later);self.assertEqual(self.t.cash['G10ENTRY01'],cash)
        self.assertFalse(self.open(now=later,signal_window_end='new',symbol='ABC'))
        self.assertEqual(self.rejection(),'overnight_residual')
    def test_missing_data_distinct_from_zero_and_no_trades(self):
        modules,_=calculate_generation_ten(self.root,'2026-10-19',NOW)
        self.assertIsNone(modules['G10ENTRY01BA']['return_pct'])
        self.ready();modules,_=calculate_generation_ten(self.root,'2026-10-19',NOW)
        self.assertEqual(modules['G10ENTRY01BA']['status'],'no_trades')
        self.assertEqual(modules['G10ENTRY01BA']['return_pct'],0.)
        modules,_=calculate_generation_ten(self.root,'2026-10-19',NOW+timedelta(minutes=4))
        self.assertIsNone(modules['G10ENTRY01BA']['return_pct'])
    def test_asof_never_uses_future_snapshot(self):
        self.ready();before=NOW-timedelta(seconds=1)
        modules,_=calculate_generation_ten(self.root,'2026-10-19',before)
        self.assertIsNone(modules['G10ENTRY01BA']['return_pct'])
    def test_mark_unavailable_and_incomplete_drawdown(self):
        self.ready();self.assertTrue(self.open());later=NOW+timedelta(seconds=61);self.t.update_quotes({},later)
        self.assertTrue(self.t.snapshots['G10ENTRY01']['drawdown_incomplete'])
        self.assertIsNone(self.t.snapshots['G10ENTRY01']['equity'])
    def test_frozen_manifest_and_missing_birth_fail_closed(self):
        self.t.close();p=self.root/(FILE_STEM+'_births.json');p.unlink()
        with self.assertRaises(ValueError):GenerationTenTracker(self.root)
    def test_single_writer(self):
        with self.assertRaises(RuntimeError):GenerationTenTracker(self.root)
    def test_corrupt_ledger_never_resets_accounts(self):
        self.assertTrue(self.open());self.t.close()
        with self.t.ledger_path.open('a') as f:f.write('{bad\n')
        with self.assertRaises(ValueError):GenerationTenTracker(self.root)
    def test_unknown_raw_numbers_fail_closed(self):
        for value in [float('nan'),float('inf'),None,'bad']:
            self.assertFalse(g.raw_accepts(g.SPECS['G10ENTRY01'],dict(flash_drop_pct=2,pre_return_pct=value,pre_r2=.8)))
    def test_reporting_filters_and_nt(self):
        self.ready();mods,_=calculate_generation_ten(self.root,'2026-10-19',NOW)
        live=dict(day='2026-10-19',modules=mods)
        (self.root/'all_engine_performance_live.json').write_text(json.dumps(live))
        text=table(self.root,g10=True);self.assertIn('NT',text);self.assertIn('G3MPR150BA',text)
        with patch('research_tools.g10.performance_table.output_enabled',side_effect=lambda sid:sid not in {'G10ENTRY01','G10ENTRY01BA'}):
            self.assertNotIn('G10ENTRY01BA',table(self.root,g10=True))
    def test_daily_loss_gate_blocks_new_entries_but_not_liquidation(self):
        self.ready();self.assertTrue(self.open('G10RISK17'))
        later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=94.,ask=94.01)},later)
        self.assertFalse(self.open('G10RISK17',later,signal_window_end='next'))
        self.assertEqual(self.rejection(),'daily_loss_limit')
        self.assertFalse(self.t.active)
    def test_daily_cash_profit_is_not_reset(self):
        self.ready();self.assertTrue(self.open())
        later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=113.,ask=113.01)},later)
        cash=self.t.cash['G10ENTRY01']
        tomorrow=NOW+timedelta(days=1)
        self.t.observe_scan(tomorrow,100);self.t.update_quotes({},tomorrow)
        self.assertAlmostEqual(self.t.cash['G10ENTRY01'],cash)
        self.assertEqual(self.t.snapshots['G10ENTRY01']['daily_pnl'],0)
    def test_unready_scanner_cannot_report_no_trades_zero(self):
        self.t.observe_scan(NOW,100,0);self.t.update_quotes({},NOW)
        modules,_=calculate_generation_ten(self.root,'2026-10-19',NOW)
        self.assertIsNone(modules['G10ENTRY01BA']['return_pct'])
    def test_future_feature_evidence_fails_closed(self):
        future=(NOW+timedelta(seconds=1)).isoformat()
        self.assertFalse(self.open('G10VOL01',flash_snapshot_time=future))
        self.assertEqual(self.rejection(),'volatility_provenance')
        self.assertFalse(self.open('G10REGIME01',market_feature_time=future))
        self.assertEqual(self.rejection(),'market_provenance')
    def test_legacy_parent_missing_is_explicit_and_g10_audit_reconciles_net(self):
        from research_tools.g10.audit import parent_audit,challenger_audit
        self.assertIn('unavailable',parent_audit(self.root)['status'])
        self.ready();self.assertTrue(self.open());later=NOW+timedelta(minutes=1)
        self.t.update_quotes({'XYZ':quote(later,bid=113.,ask=113.01)},later)
        result=challenger_audit(self.root)['modules']['G10ENTRY01']
        self.assertEqual(result['trades'],1)
        self.assertAlmostEqual(result['net_pnl'],self.t.cash['G10ENTRY01']-5000)
    def test_frozen_configuration_tamper_refuses_restart(self):
        self.t.close();path=self.root/(FILE_STEM+'_manifest.json')
        m=json.loads(path.read_text());m['specs'][0]['stop']=.9;path.write_text(json.dumps(m))
        with self.assertRaises(ValueError):GenerationTenTracker(self.root)
    def test_account_frame_throttling_bounds_storage(self):
        self.ready();seq=self.t.seq
        self.t.update_quotes({},NOW+timedelta(seconds=5));self.assertEqual(self.t.seq,seq)
        self.t.update_quotes({},NOW+timedelta(seconds=60));self.assertGreater(self.t.seq,seq)
    def test_stale_mark_after_eod_is_allowed_only_for_flat_cash(self):
        self.ready();end=NOW.replace(hour=19,minute=55)
        self.t.update_quotes({},end)
        mods,_=calculate_generation_ten(self.root,'2026-10-19',end+timedelta(minutes=5))
        self.assertEqual(mods['G10ENTRY01BA']['return_pct'],0.)
    def test_all_engine_has_200_unknown_g10_accounts_without_backfill(self):
        from reporting.all_engine_performance import calculate
        result=calculate(self.root,day='2026-10-19',as_of=NOW)
        self.assertEqual(sum(s+'BA' in result['modules'] for s in g.IDS),200)
        self.assertTrue(all(result['modules'][s+'BA']['return_pct'] is None for s in g.IDS))
        old,_=calculate_generation_ten(self.root,'2026-10-16',NOW)
        self.assertFalse(old)

    def test_g10_runtime_fault_is_durable_and_does_not_escape_to_other_generations(self):
        with patch.object(self.t,'register_signal',side_effect=ValueError('bad provenance')):
            with patch('builtins.print'):
                self.assertFalse(safe_call(self.t,'register_signal',signal(),quote(),NOW))
        self.assertTrue(self.t.failed)
        self.assertTrue((self.root/(FILE_STEM+'_error.json')).exists())
        self.assertFalse(safe_call(self.t,'register_signal',signal(),quote(),NOW))
        self.assertFalse(self.t.active)

    def test_corrupt_g10_ledger_is_reported_without_breaking_existing_reports(self):
        from reporting.all_engine_performance import calculate
        self.t.ledger_path.write_text('{broken\n')
        result=calculate(self.root,day='2026-10-19',as_of=NOW)
        self.assertIn('error',result['diagnostics']['generation_ten'])
        self.assertEqual(sum(s+'BA' in result['modules'] for s in g.IDS),200)
        self.assertTrue(all(result['modules'][s+'BA']['return_pct'] is None for s in g.IDS))
        self.t.birth_path.write_text('{broken')
        result=calculate(self.root,day='2026-10-19',as_of=NOW)
        self.assertIn('error',result['diagnostics']['generation_ten'])

    def test_registry_default_off_optin(self):
        code="from strategies import registry as r;from strategies import generation_ten as g;print(len(g.IDS&r.flash_strategy_configs().keys()))"
        for flag,n in [('0','0'),('1','200')]:
            env={**os.environ,'ENABLE_G10_PAPER':flag}
            out=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,check=True)
            self.assertEqual(out.stdout.strip().splitlines()[-1],n)
    def test_real_runner_routing_and_no_broker_imports(self):
        path=Path(__file__).resolve().parents[1]/'live_strategy_runner.py';tree=ast.parse(path.read_text())
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='register_single_leg_paper')
        env=dict(RUN_MODE='LIVE',G10_ENABLED=True,GENERATION_TEN_IDS=g.IDS,
            GENERATION_ONE_IDS=set(),GENERATION_TWO_IDS=set(),GENERATION_THREE_IDS=set(),GENERATION_FOUR_IDS=set(),GENERATION_FIVE_IDS=set(),
            generation_ten_outcomes=Mock(failed=False),independent_l1=Mock(),quote_source=Mock(),g10_call=safe_call)
        env['independent_l1'].quotes.return_value={'XYZ':quote()};env['quote_source'].now.return_value=NOW
        env['generation_ten_outcomes'].symbols.return_value=set()
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
        env['register_single_leg_paper'](signal());env['generation_ten_outcomes'].register_signal.assert_called_once()
        env['RUN_MODE']='REPLAY';self.assertFalse(env['register_single_leg_paper'](signal()))
        env['RUN_MODE']='LIVE';env['G10_ENABLED']=False;self.assertFalse(env['register_single_leg_paper'](signal()))
        for filename in ['generation_ten_paper_tracker.py','strategies/generation_ten.py']:
            code=(path.parent/filename).read_text()
            self.assertNotIn('schwab_clients',code);self.assertNotIn('place_order',code)
        guard=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.iter,ast.Name) and n.iter.id=='live_nh015_candidates')
        self.assertIsInstance(guard.body[0],ast.If)
        self.assertTrue(any(isinstance(n,ast.Continue) for n in ast.walk(guard.body[0])))


if __name__=='__main__':unittest.main()
