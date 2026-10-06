"""G3 isolated durable paper execution; production activation is opt-in."""
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from strategies import generation_three as g3
from paper_outcome_tracker import _utc

FILE_STEM='paper_generation_three_bidask_independent'
IDS=g3.ALL_IDS

class GenerationThreeBidAskTracker(GenerationTwoBidAskTracker):
    IDS=IDS
    FILE_STEM=FILE_STEM
    flash_catalog=g3
    minute_catalog=g3.MINUTE_CATALOG
    EXECUTION_MODEL='GENERATION_THREE_BIDASK_V1'

    def register_signal(self,signal,quote,now):
        # The old confirmation reference remains recorded, but execution geometry
        # is established from the actual ASK, including the nominal risk size.
        sid=signal.get('strategy_id')
        if sid not in self.IDS:return False
        s=self.spec_for(sid);row=dict(signal);ask=g3.num((quote or {}).get('ask'))
        row['research_metadata']={**g3.metadata(sid),'admission_evidence':{
            k:row.get(k) for k in ('timestamp','completed_minute','entry_price','flash_drop_pct',
                                 'pre_return_pct','pre_r2','pre30_return_std_pct','original_target_price')}}
        if ask>0:
            row['confirmation_reference_price']=row.get('entry_price')
            row['stop_price']=ask*(1-s.stop)
            original=g3.num(row.get('original_target_price',row.get('target_price')))
            row['target_price']=(ask+(original-ask)*s.target_scale if sid in g3.IDS else ask*(1+s.target_pct/100))
            row['checkpoint_clock']='actual_fill'
            row['research_metadata']['admission_evidence'].update(
                execution_ask=ask,execution_bid=g3.num((quote or {}).get('bid')),
                actual_stop=row['stop_price'],actual_target=row['target_price'])
        return super().register_signal(row,quote,now)

    def entry_gate(self,signal,quote,now):
        reason=super().entry_gate(signal,quote,now)
        if reason:return reason
        s=self.spec_for(signal['strategy_id']);ask=g3.num(quote.get('ask'))
        if not s.min_price<=ask<=s.max_price:return 'g3_executable_price_outside_cohort'
        # Recheck the time window at execution, not only candidate timestamp.
        if not g3.time_admits(s,now):return 'g3_outside_execution_time_window'
        ts=g3.timestamp(signal.get('timestamp'))
        if signal['strategy_id'] in g3.MINUTE_IDS:
            completed=g3.timestamp(signal.get('completed_minute'))
            if completed!=ts or ts is None or ts.second or ts.microsecond:return 'g3_missing_completed_minute_provenance'
        if s.cooldown_seconds:
            for row in self._admitted_entries(signal['strategy_id']):
                opened=_utc(row['entry_timestamp'])
                if 0 <= (now-opened).total_seconds() < s.cooldown_seconds:return 'g3_admitted_fill_cooldown'
        return None

    def __init__(self,*args,**kwargs):
        self._last_admitted={}
        self._symbol_cursor=0
        super().__init__(*args,**kwargs)

    def symbols(self,limit=400):
        symbols=sorted(self.by_symbol)
        if not symbols:return set()
        start=self._symbol_cursor % len(symbols)
        selected=(symbols[start:]+symbols[:start])[:limit]
        self._symbol_cursor=(start+len(selected)) % len(symbols)
        return set(selected)

    def _recover_rows(self,handle):
        # Recovery must remember cooldown even after a completed trade disappears.
        def observed():
            import json
            for line in handle:
                try:
                    row=json.loads(line)
                    if row.get('event_type')=='PAPER_ENTRY' and row.get('strategy_id') in self.IDS:
                        self._last_admitted[row['strategy_id']]=row
                except (ValueError,TypeError):pass
                yield line
        super()._recover_rows(observed())

    def _append(self,row):
        super()._append(row)
        if row.get('event_type')=='PAPER_ENTRY':self._last_admitted[row['strategy_id']]=row.copy()

    def _admitted_entries(self,sid):
        row=self._last_admitted.get(sid)
        return [row] if row else []

    def _update_k_checkpoint(self,record,price,now):
        # Established exit state machine uses signal age. G3 deliberately uses
        # fill age so processing delays cannot consume the checkpoint budget.
        original=record['signal_timestamp']
        try:
            record['signal_timestamp']=record['entry_timestamp']
            return super()._update_k_checkpoint(record,price,now)
        finally:record['signal_timestamp']=original
