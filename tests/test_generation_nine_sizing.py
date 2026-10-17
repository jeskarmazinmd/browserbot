"""Execution regression tests; synthetic admissions are not profit evidence."""
import copy
import json
import math
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import unittest
from tests import test_generation_nine as base
from tests.test_generation_nine import NOW, book, decision
from strategies import generation_nine as g
from generation_nine_paper_tracker import (size_pair, fee, mark_group, EXECUTION_VERSION,
    LEGACY_TRACKER_HASH, FILE_STEM, GenerationNineTracker, source_hashes)


class SizingTests(unittest.TestCase):
    setUp = base.Tests.setUp
    tearDown = base.Tests.tearDown
    books = base.Tests.books
    # Reuse the established lock, paper gate and temporary-ledger harness.
    def solve(self, prices=(100.,760.), weights=(1.,1.), equity=5000., sizes=(1000,1000), spec=None):
        raw=decision()['legs']
        for x,w in zip(raw,weights):x['weight']=w
        q={x['symbol']:book(price=p,size=n) for x,p,n in zip(raw,prices,sizes)}
        return size_pair(raw,q,NOW,spec or g.SPECS['G9Z01'],equity,{},'G9Z01')

    def test_coarse_spy_and_unreachable_hedges(self):
        r,reason=self.solve();self.assertIsNone(reason)
        self.assertGreater(r['legs'][1]['shares'],0)
        self.assertLessEqual(r['collateral_reserved'],5000)
        self.assertLessEqual(r['hedge_relative_error'],.10)
        self.assertEqual(self.solve(prices=(3000.,760.))[1],'hedge_ratio_mismatch')
        self.assertEqual(self.solve(prices=(4500.,760.))[1],'insufficient_whole_share_allocation')
        self.assertEqual(self.solve(equity=500.)[1],'insufficient_collateral_or_buying_power')

    def test_separate_size_and_liquidity_reasons(self):
        raw=decision()['legs'];q=self.books();q['SPY'].pop('bid_size_raw')
        self.assertEqual(size_pair(raw,q,NOW,g.SPECS['G9Z01'],5000,{},'G9Z01')[1],'missing_quote_size')
        self.assertEqual(self.solve(sizes=(1000,0))[1],'insufficient_displayed_liquidity')
        r,reason=self.solve(sizes=(1000,1));self.assertIsNone(reason)
        self.assertEqual(r['legs'][1]['shares'],1)
        self.assertEqual(self.solve(sizes=(1000,1),spec=replace(g.SPECS['G9Z01'],participation=.5))[1],
                         'insufficient_displayed_liquidity')

    def test_fees_prevent_full_equity_pair_and_both_sides(self):
        r,reason=self.solve(prices=(2499.99,2500.01),equity=5000.)
        self.assertIsNone(r);self.assertEqual(reason,'insufficient_collateral_or_buying_power')
        spec=replace(g.SPECS['G9Z01'],slippage_bps=2.)
        r,_=self.solve(spec=spec);long,short=r['legs']
        self.assertAlmostEqual(long['entry_price'],100.01*1.0002)
        self.assertAlmostEqual(short['entry_price'],759.99*.9998)
        self.assertAlmostEqual(fee(r['legs']),sum(max(.01,.005*x['shares']) for x in r['legs']))
        row=dict(strategy_id='G9Z01',legs=r['legs'],opened_at=NOW.isoformat(),
                 entry_fee=fee(r['legs']),gross_notional_used=sum(x['shares']*x['entry_price'] for x in r['legs']))
        q={'AAPL':book(),'SPY':book(price=760.)}
        m=mark_group(row,q,NOW,spec)
        self.assertAlmostEqual(m['exit_legs'][0]['exit_price'],99.99*.9998)
        self.assertAlmostEqual(m['exit_legs'][1]['exit_price'],760.01*1.0002)
        self.assertLess(m['pnl'],0.)
        self.assertEqual(m['borrow_fee'],0.)

    def test_cumulative_equity_survives_restart_and_next_day(self):
        self.assertTrue(self.t.open(decision(),self.books(),NOW))
        from datetime import timedelta
        later=NOW+timedelta(minutes=121)
        q={'AAPL':book(later,90.),'SPY':book(later,110.)}
        self.t.update(q,later)
        loss=sum(self.t.realized.values());self.assertLess(loss,0)
        self.t.close();self.t=GenerationNineTracker(self.root,now_provider=lambda:later)
        nextday=NOW+timedelta(days=3)
        self.assertTrue(self.t.open(decision(now=nextday),self.books(nextday),nextday))
        row=self.t.active['G9Z01'];self.assertAlmostEqual(row['equity_before'],5000+loss)
        self.assertLessEqual(row['collateral_reserved'],5000+loss)

    def test_versioned_legacy_migration_preserves_bytes(self):
        self.t.close()
        manifest=self.root/(FILE_STEM+'_manifest.json')
        m=json.loads(manifest.read_text());m['sources']['generation_nine_paper_tracker.py']=LEGACY_TRACKER_HASH
        manifest.write_text(json.dumps(m));old=manifest.read_bytes()
        self.t.execution_path.unlink()
        record=dict(event='REJECT',strategy_id='G9Z01',timestamp=NOW.isoformat(),reason='whole_share_or_liquidity')
        ledger=self.root/(FILE_STEM+'_outcomes.jsonl');ledger.write_text(json.dumps(record)+'\n');prior=ledger.read_bytes()
        births=self.t.birth_path.read_bytes()
        self.t=GenerationNineTracker(self.root,now_provider=lambda:NOW)
        self.assertEqual(manifest.read_bytes(),old);self.assertEqual(ledger.read_bytes(),prior)
        self.assertEqual(self.t.birth_path.read_bytes(),births)
        self.assertTrue(self.t.open(decision(),self.books(),NOW))
        self.assertEqual(self.t.epoch_counts['G9_LEGACY_V1']['REJECT'],1)
        self.assertEqual(self.t.epoch_counts[EXECUTION_VERSION]['OPEN'],1)
        self.assertTrue(ledger.read_bytes().startswith(prior))

    def test_production_tape_whole_share_pair(self):
        f=json.loads((Path(__file__).parent/'fixtures/g9_observed_pair.json').read_text())
        now=g.utc(f['observed_at']);symbol=next(x for x in f['quotes'] if x!='SPY')
        raw=[dict(symbol=symbol,side='LONG',weight=1.),dict(symbol='SPY',side='SHORT',weight=1.)]
        for reverse in [False,True]:
            for leg in raw:leg['side']=('SHORT' if leg['symbol']==symbol else 'LONG') if reverse else ('LONG' if leg['symbol']==symbol else 'SHORT')
            r,reason=size_pair(raw,f['quotes'],now,g.SPECS['G9Z01'],5000.,{},'G9Z01')
            self.assertIsNone(reason);self.assertLessEqual(r['collateral_reserved'],5000.)
            self.assertLessEqual(r['hedge_relative_error'],.10)
            self.assertEqual([x['shares'] for x in r['legs']],[6,3])

    def test_disabled_gate_all_400_and_status(self):
        with patch.dict('os.environ',{'ENABLE_G9_PAPER':'0'}):
            for sid in g.IDS:self.assertFalse(self.t.open(decision(sid),self.books(),NOW))
        self.t.status();s=json.loads((self.root/(FILE_STEM+'_status.json')).read_text())
        self.assertEqual(s['max_gross_group_notional'],5000.)
        self.assertFalse(s['broker_margin_verified']);self.assertFalse(s['broker_buying_power_verified'])
        self.assertFalse(s['short_locate_verified']);self.assertFalse(s['broker_execution_enabled'])

    def test_weighted_tolerance_not_equal_dollars_all_400(self):
        for spec in g.CATALOG:
            target=1.3*spec.hedge_scale
            r,reason=self.solve(prices=(200.,760.),weights=(1.,target),spec=spec)
            self.assertIsNone(reason,spec.strategy_id)
            a,b=r['legs']
            actual=b['shares']*b['entry_price']/(a['shares']*a['entry_price'])
            self.assertLessEqual(abs(actual/target-1),.10+1e-12,spec.strategy_id)
            self.assertAlmostEqual(r['hedge_relative_error'],abs(actual/target-1))
        r,reason=self.solve(weights=(1.,2.5));self.assertIsNone(reason)
        a,b=r['legs'];ratio=b['shares']*b['entry_price']/(a['shares']*a['entry_price'])
        self.assertGreater(ratio,2.25)

    def test_tampered_execution_manifest_fails_closed(self):
        self.t.close()
        p=self.root/(FILE_STEM+'_execution_v2.json');r=json.loads(p.read_text())
        r['policy']['max_gross']=10000;p.write_text(json.dumps(r))
        with self.assertRaises(ValueError):GenerationNineTracker(self.root,now_provider=lambda:NOW)

    def test_reporting_identifies_execution_epoch_and_unverified_broker(self):
        from reporting.generation_nine_performance import calculate_generation_nine
        self.assertTrue(self.t.open(decision(),self.books(),NOW))
        mods,diagnostics=calculate_generation_nine(self.root,'2026-10-16',NOW,self.books())
        self.assertEqual(mods['G9Z01']['execution_versions'],[EXECUTION_VERSION])
        self.assertFalse(mods['G9Z01']['broker_margin_verified'])
        self.assertFalse(mods['G9Z01']['broker_execution_enabled'])
        self.assertEqual(diagnostics['counts_by_execution_version'][EXECUTION_VERSION]['OPEN'],1)

    def test_weekend_uses_fresh_waiting_worker_not_old_g9_timestamp(self):
        from datetime import timedelta
        from research_tools.verify_generation_nine import inspect
        weekend=NOW+timedelta(days=1)
        worker=self.root/'statarb_shadow_status.json'
        state=dict(updated_at=weekend.isoformat(),status='WAITING_REGULAR_MARKET',broker_execution_enabled=False)
        worker.write_text(json.dumps(state))
        result=inspect(self.root,now=weekend)
        self.assertTrue(all(result['checks'].values()),result)
        self.assertFalse(result['regular_market'])
        self.assertGreater(result['status_age_seconds'],180)
        state['updated_at']=(weekend-timedelta(seconds=181)).isoformat();worker.write_text(json.dumps(state))
        self.assertFalse(inspect(self.root,now=weekend)['checks']['fresh_status'])
        state.update(updated_at=weekend.isoformat(),status='ERROR_BACKOFF');worker.write_text(json.dumps(state))
        self.assertFalse(inspect(self.root,now=weekend)['checks']['fresh_status'])
        worker.unlink()
        self.assertFalse(inspect(self.root,now=weekend)['checks']['fresh_status'])
        self.assertTrue(inspect(self.root,now=NOW)['checks']['fresh_status'])

    def test_legacy_production_verifier_understands_v2_cap_and_migration(self):
        from research_tools.g9.verify_production import inspect
        self.assertTrue(self.t.open(decision(),self.books(),NOW))
        self.t.status()
        p=self.t.manifest_path;m=json.loads(p.read_text())
        m['sources']['generation_nine_paper_tracker.py']=LEGACY_TRACKER_HASH;p.write_text(json.dumps(m))
        with patch('research_tools.g9.verify_production.inspect_v2',return_value=dict(checks={})), patch.dict('os.environ',{'ENABLE_G9_RETIREMENTS':'1'}):
            result=inspect(self.root,allow_warmup=True)
        self.assertGreater(self.t.active['G9Z01']['gross_notional_used'],1000)
        self.assertFalse(any('hash mismatch' in x or 'Frozen rule' in x or 'Oversized' in x for x in result['errors']),result)
