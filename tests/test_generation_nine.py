import copy
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import json
import math
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from strategies import generation_nine as g
from strategies.generation_nine_retirement import plan,entry_retired
from generation_nine_paper_tracker import GenerationNineTracker,FILE_STEM,mark_group
from reporting.generation_nine_performance import calculate_generation_nine
from statarb_shadow_worker import g9_cycle,normalize
from statarb2_strategies.strategy_sthedge2 import Strategy as Parent

NOW=datetime(2026,10,16,16,tzinfo=timezone.utc)

def book(now=NOW,price=100.,size=1000):
    return dict(bid=price-.01,ask=price+.01,bid_size_raw=size,ask_size_raw=size,
                quote_time_ms=now.timestamp()*1000,realtime=True)


def decision(sid='G9Z01',now=NOW):
    return dict(strategy_id=sid,timestamp=now.isoformat(),paper_only=True,live_order_placement=False,
                population_hash=g.POPULATION_HASH,research=dict(residual_z=-2.5),
                legs=[dict(symbol='AAPL',side='LONG',weight=1.),dict(symbol='SPY',side='SHORT',weight=1.)])


class Tests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'ENABLE_G9_PAPER':'1','ENABLE_G9_RETIREMENTS':'0'})
        self.env.start();self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.t=GenerationNineTracker(self.root,now_provider=lambda:NOW)
    def tearDown(self):
        self.t.close();self.tmp.cleanup();self.env.stop()
    def books(self,now=NOW):return {'AAPL':book(now),'SPY':book(now)}
    def test_exact_retirement_and_preserved_parent(self):
        p=plan();self.assertEqual(len(p['retained_report_ids']),130);self.assertEqual(len(p['retired_report_ids']),466)
        with patch.dict(os.environ,{'ENABLE_G9_RETIREMENTS':'1'}):
            self.assertFalse(any(entry_retired(x) for x in p['retained_report_ids']))
            self.assertTrue(all(entry_retired(x) for x in p['retired_report_ids']))
            self.assertTrue(all(entry_retired(x.removesuffix('BA')) for x in p['retired_report_ids']))
            self.assertFalse(entry_retired('STHEDGE2'))
    def test_population_unique_and_all_400_can_admit(self):
        self.assertEqual(len(g.IDS),400)
        for s in g.CATALOG:
            # Fixed future birth, choose a valid session time for every session cohort.
            et=NOW.astimezone(g.NY).replace(hour=s.first_minute//60,minute=s.first_minute%60)
            t=et.astimezone(timezone.utc)+timedelta(days=3)
            q=self.books(t)
            for b in q.values():b.update(bid=99.999,ask=100.001)
            self.assertTrue(self.t.open(decision(s.strategy_id,t),q,t),s.strategy_id)
        self.assertEqual(len(self.t.active),400)
        for r in self.t.active.values():self.assertLessEqual(r['gross_notional_used'],1000.)
    def test_both_legs_fresh_liquid_and_finite(self):
        for bad in ['stale','future','nan','crossed','delayed','size','missing_size']:
            with self.subTest(bad=bad):
                q=self.books();hedge=q['SPY']
                if bad=='stale':hedge['quote_time_ms']-=6000
                if bad=='future':hedge['quote_time_ms']+=1
                if bad=='nan':hedge['ask']=float('nan')
                if bad=='crossed':hedge['ask']=1
                if bad=='delayed':hedge['realtime']=False
                if bad=='size':hedge['bid_size_raw']=0
                if bad=='missing_size':hedge.pop('bid_size_raw')
                self.assertFalse(self.t.open(decision(),q,NOW))
        self.assertFalse(self.t.active)
    def test_realized_pnl_sides_fees_and_reporting(self):
        self.assertTrue(self.t.open(decision(),self.books(),NOW));e=copy.deepcopy(self.t.active['G9Z01'])
        later=NOW+timedelta(minutes=1);q={'AAPL':book(later,price=102.),'SPY':book(later,price=98.)}
        expected=mark_group(e,q,later,g.SPECS['G9Z01'])
        self.t.update(q,later);self.assertFalse(self.t.active)
        rows=[json.loads(x) for x in self.t.ledger.read_text().splitlines()]
        self.assertEqual(rows[-1]['exit_reason'],'TARGET');self.assertAlmostEqual(rows[-1]['pnl'],expected['pnl'])
        self.assertGreater(rows[-1]['borrow_fee'],0)
        mods,_=calculate_generation_nine(self.root,'2026-10-16',later,q)
        self.assertAlmostEqual(mods['G9Z01']['return_pct'],expected['pnl']/50)
    def test_pending_exit_persists_and_fills_only_complete_pair(self):
        self.t.open(decision(),self.books(),NOW)
        later=NOW+timedelta(minutes=121);q=self.books(later);q['SPY']['ask_size_raw']=0
        self.t.update(q,later);self.assertIn('G9Z01',self.t.active)
        self.assertEqual(self.t.active['G9Z01']['pending_exit_reason'],'TIMEOUT')
        self.t.close();self.t=GenerationNineTracker(self.root,now_provider=lambda:later)
        self.assertEqual(self.t.active['G9Z01']['pending_exit_reason'],'TIMEOUT')
        end=later+timedelta(minutes=1);self.t.update(self.books(end),end)
        self.assertFalse(self.t.active);self.assertEqual(self.t.completed,1)
    def test_missing_open_mark_unknown_never_zero(self):
        self.t.open(decision(),self.books(),NOW)
        mods,_=calculate_generation_nine(self.root,'2026-10-16',NOW+timedelta(minutes=1),{})
        self.assertIsNone(mods['G9Z01']['return_pct']);self.assertEqual(mods['G9Z02']['return_pct'],0.)
        before,_=calculate_generation_nine(self.root,'2026-10-15',NOW-timedelta(days=1),{})
        self.assertFalse(before)
    def test_recovery_births_rules_lock_and_corruption(self):
        self.t.open(decision(),self.books(),NOW);births=self.t.births.copy()
        with self.assertRaises(RuntimeError):GenerationNineTracker(self.root,now_provider=lambda:NOW)
        self.t.close();self.t=GenerationNineTracker(self.root,now_provider=lambda:NOW+timedelta(days=1))
        self.assertEqual(self.t.births,births);self.assertEqual(len(self.t.active),1)
        self.assertFalse(self.t.open(decision(),self.books(),NOW))
        self.t.close();p=self.root/(FILE_STEM+'_manifest.json');m=json.loads(p.read_text());m['population_hash']='altered';p.write_text(json.dumps(m))
        with self.assertRaises(ValueError):GenerationNineTracker(self.root)
    def test_paper_only_birth_contract_and_disable_preserves_exit(self):
        for change in [dict(paper_only=False),dict(live_order_placement=True),dict(population_hash='bad'),dict(timestamp=(NOW-timedelta(minutes=1)).isoformat())]:
            d=decision();d.update(change);self.assertFalse(self.t.open(d,self.books(),NOW))
        self.t.open(decision(),self.books(),NOW)
        with patch.dict(os.environ,{'ENABLE_G9_PAPER':'0'}):
            later=NOW+timedelta(minutes=121);self.t.update(self.books(later),later)
        self.assertFalse(self.t.active)
    def test_no_reusing_quote_depth_within_portfolio(self):
        self.t.open(decision(),self.books(),NOW)
        self.assertFalse(self.t.open(decision(),self.books(),NOW))
        self.assertTrue(self.t.open(decision('G9Z02'),self.books(),NOW))
        self.assertEqual(len(self.t.active),2)
    def test_carry_unknown_and_no_free_new_cash(self):
        self.t.open(decision(),self.books(),NOW)
        later=NOW+timedelta(days=3)
        self.t.update(self.books(later),later)
        self.assertFalse(self.t.active)
        self.assertFalse(self.t.open(decision(now=later),self.books(later),later))
        mods,_=calculate_generation_nine(self.root,'2026-10-19',later,self.books(later))
        self.assertIsNone(mods['G9Z01']['return_pct'])
    def test_contiguous_alignment_duplicate_gap_and_session_reset(self):
        p=g.Population()
        for i in range(102):p.observe(NOW+timedelta(minutes=i),self.books(NOW+timedelta(minutes=i)))
        self.assertIsNotNone(p.feature(g.SPECS['G9Z01'],'AAPL'))
        self.assertFalse(p.observe(NOW,self.books()))
        t=NOW+timedelta(minutes=103);p.observe(t,{'SPY':book(t)})
        self.assertIsNone(p.feature(g.SPECS['G9Z01'],'AAPL'))
        p.observe(t+timedelta(days=1),self.books(t+timedelta(days=1)))
        self.assertEqual(len(p.hist['SPY']),1)
    def test_parent_signal_parity_with_synchronized_contiguous_stream(self):
        parent=Parent();pop=g.Population();rng=random.Random(91);a=b=100.;found=0
        start=NOW-timedelta(minutes=110)
        for i in range(220):
            t=start+timedelta(minutes=i);r=rng.gauss(0,.0006);b*=1+r
            a*=1+.9*r+rng.gauss(0,.0002)+(0.001 if 105<=i<115 else 0.)
            q={'AAPL':book(t,a),'SPY':book(t,b)}
            pop.observe(t,q);d=pop.decision(g.SPECS['G9Z01'],t)
            parent.last=None;old=parent.evaluate(dict(timestamp=t,quotes=q))
            if old:
                found+=1;self.assertIsNotNone(d)
                self.assertEqual(d['legs'][0]['side'],old[0]['legs'][0]['side'])
                self.assertAlmostEqual(d['research']['residual_z'],old[0]['research']['residual_z'],places=10)
        self.assertGreater(found,0)
    def test_future_report_excludes_later_closes(self):
        self.t.open(decision(),self.books(),NOW)
        later=NOW+timedelta(minutes=121);self.t.update(self.books(later),later)
        mods,_=calculate_generation_nine(self.root,'2026-10-16',NOW,self.books())
        self.assertEqual(mods['G9Z01']['open_taken'],1);self.assertEqual(mods['G9Z01']['closed_taken'],0)
    def test_every_catalog_rule_has_reachable_admission_and_threshold_contrast(self):
        for spec in g.CATALOG:
            pop=g.Population();symbol=sorted(g.COHORTS[spec.universe])[0] if spec.universe!='ALL' else 'AAPL'
            now=NOW.astimezone(g.NY).replace(hour=spec.first_minute//60,minute=spec.first_minute%60).astimezone(timezone.utc)
            q=book(now);q.update(bid=99.999,ask=100.001)
            pop.current={symbol:q,'SPY':q}
            z=spec.entry_z+.2
            if spec.direction=='LONG':z=-z
            f=dict(long_beta=(spec.beta_min+spec.beta_max)/2,short_beta=(spec.beta_min+spec.beta_max)/2,
                   beta_drift=0.,residual_z=z,residual_sd_bps=(spec.min_sd_bps+min(30.,spec.max_sd_bps))/2,
                   market_return=-.1 if spec.market_filter=='DOWN' else .1,last_residual=-z*.1)
            with patch.object(pop,'feature',return_value=f):
                self.assertIsNotNone(pop.decision(spec,now),spec.strategy_id)
                f['residual_z']=spec.entry_z*.99
                self.assertIsNone(pop.decision(spec,now),spec.strategy_id)

    def test_native_rv_retirement_blocks_new_entries_without_touching_exits(self):
        from options_rv_paper_tracker import OptionsRVTracker
        t=OptionsRVTracker.__new__(OptionsRVTracker)
        with patch.dict(os.environ,{'ENABLE_G9_RETIREMENTS':'1'}):
            self.assertFalse(t.open({'strategy_id':'RVCALLCR1'},NOW))

    def test_nonfinite_recorded_profit_refuses_recovery(self):
        self.t.open(decision(),self.books(),NOW)
        later=NOW+timedelta(minutes=121);self.t.update(self.books(later),later)
        self.t.close();lines=self.t.ledger.read_text().splitlines();r=json.loads(lines[-1]);r['pnl']=float('nan')
        self.t.ledger.write_text('\n'.join(lines[:-1]+[json.dumps(r)])+'\n')
        with self.assertRaises(ValueError):GenerationNineTracker(self.root,now_provider=lambda:later)

    def test_normalizer_preserves_execution_evidence(self):
        q=normalize('AAPL',dict(realtime=True,quote=dict(bidPrice=99.,askPrice=100.,bidSize=12,askSize=13,quoteTime=123)))
        self.assertEqual(q['bid_size_raw'],12);self.assertEqual(q['ask_size_raw'],13);self.assertEqual(q['ask_time_ms'],123)

if __name__=='__main__':unittest.main()
