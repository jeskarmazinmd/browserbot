import csv,json,tempfile,unittest
from pathlib import Path
from research_tools.g3_review.native_audit import run

class NativeAuditTests(unittest.TestCase):
    def audit(self,filename,rows):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);data=root/'data';out=root/'out';data.mkdir()
        (data/filename).write_text('\n'.join(json.dumps(x) if isinstance(x,dict) else x for x in rows)+'\n')
        run(data,out)
        def read(name):
            with (out/name).open(newline='') as f:return list(csv.DictReader(f))
        return read('native_closed_trades.csv'),read('native_module_metrics.csv'),json.loads((out/'native_quality.json').read_text())
    def test_option_exit_alias_preserves_unclosed_and_bad_line(self):
        trades,metrics,q=self.audit('options_paper_outcomes.jsonl',[
            dict(event_type='OPTION_ENTRY',group_id='a',strategy_id='OPT',timestamp='2026-09-30T14:00:00Z',legs=[dict(symbol='contract')]),
            dict(event_type='OPTION_EXIT',group_id='a',strategy_id='OPT',exit_time='2026-09-30T15:00:00Z',pnl=-80),
            dict(event_type='OPTION_ENTRY',group_id='b',strategy_id='OPT',timestamp='2026-09-30T15:00:00Z'),'{broken'])
        self.assertEqual(len(trades),1);self.assertEqual(float(trades[0]['closed_pnl']),-80)
        self.assertEqual(float(trades[0]['hold_seconds']),3600)
        self.assertEqual(q[0]['open_keys'],1);self.assertEqual(q[0]['malformed_line_numbers'],[4])
    def test_rv_reused_setup_is_two_trades_with_corrected_legacy_cashflow(self):
        trades,metrics,q=self.audit('options_rv_paper_outcomes.jsonl',[
            dict(strategy_id='RV',setup_id='same',opened_at='2026-08-10T14:00:00Z',closed_at='2026-08-10T15:00:00Z',opening_cash_flow=-22.6,closing_cash_flow=12.4,exit_contract_sides=4,pnl_dollars=-10.2),
            dict(strategy_id='RV',setup_id='same',opened_at='2026-08-10T16:00:00Z',closed_at='2026-08-10T17:00:00Z',pnl_dollars=11.4,cash_flow_sign_version=2)])
        self.assertEqual(len(trades),2);self.assertAlmostEqual(float(trades[0]['closed_pnl']),-40.2)
        self.assertAlmostEqual(float(trades[1]['closed_pnl']),11.4);self.assertEqual(q[0]['overwritten_keys'],{})
    def test_statarb_share_economics_and_one_bp_stress(self):
        trades,metrics,q=self.audit('statarb_paper_outcomes.jsonl',[
            dict(event='OPEN',group_id='a',strategy_id='ST',opened_at='2026-09-30T14:00:00Z',gross_notional_used=4000,legs=[dict(symbol='A',side='LONG',entry_price=10,shares=100),dict(symbol='B',side='SHORT',entry_price=30,shares=100)]),
            dict(event='CLOSE',group_id='a',strategy_id='ST',opened_at='2026-09-30T14:00:00Z',closed_at='2026-09-30T15:00:00Z',pnl=150,exit_legs=[dict(symbol='A',exit_price=11),dict(symbol='B',exit_price=29.5)],borrow_fees_included=False,short_locate_verified=False)])
        self.assertEqual(float(trades[0]['pnl_reconstruction_difference']),0)
        modern=next(x for x in metrics if x['period']=='modern');self.assertAlmostEqual(float(modern['closed_pnl_extra_1bp_each_side']),149.2)
        self.assertEqual(modern['borrow_fees_omitted_rows'],'1')

if __name__=='__main__':unittest.main()
