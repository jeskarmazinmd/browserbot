"""G6 isolated actual-fill portfolios; no broker capability or historical credit."""
from collections import defaultdict
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
from executable_paper_engine import executable_mark
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from paper_outcome_tracker import _utc
from strategies import generation_six as g6

FILE_STEM='paper_generation_six_bidask_independent'
IDS=g6.ALL_IDS
class GenerationSixBidAskTracker(GenerationTwoBidAskTracker):
    IDS=IDS
    FILE_STEM=FILE_STEM
    flash_catalog=g6
    minute_catalog=g6.MINUTE_CATALOG
    EXECUTION_MODEL='GENERATION_SIX_BIDASK_V1'

    def __init__(self,data_root,**kwargs):
        root=Path(data_root);manifest=root/(FILE_STEM+'_manifest.json');birth=root/(FILE_STEM+'_births.json')
        ledger=root/(FILE_STEM+'_outcomes.jsonl')
        frozen=dict(rule_version=g6.RULE_VERSION,population_hash=g6.POPULATION_HASH,
                    rule_source_sha256=g6.RULE_SOURCE_SHA256,population=400,
                    tracker_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if manifest.exists() and json.loads(manifest.read_text())!=frozen:
            raise ValueError('G6 frozen manifest changed; use new IDs for revised rules')
        if ledger.exists() and ledger.stat().st_size and (not manifest.exists() or not birth.exists()):
            raise ValueError('G6 ledger without manifest/births; refuse to reset provenance')
        if manifest.exists() and not birth.exists():raise ValueError('G6 births missing; refuse to reset provenance')
        self._verified_births=json.loads(birth.read_text()) if birth.exists() else {}
        if birth.exists() and set(self._verified_births)!=self.IDS:
            raise ValueError('G6 birth population mismatch; refuse to invent starts')
        self._last_admitted={};self._symbol_cursor=0;self._coverage_last=None
        self._coverage=defaultdict(int)
        super().__init__(data_root,**kwargs)
        self._atomic_json(manifest,frozen)
        from strategies.generation_six_retirement import enabled,plan
        activation=root/'generation_six_activation.json'
        if enabled() and not activation.exists():
            selected=plan()
            self._atomic_json(activation,dict(activated_utc=_utc(self._clock()).isoformat(),
                reason=selected['reason'],retired_report_ids=selected['retired_report_ids'],
                retained_report_ids=selected['retained_report_ids'],population_hash=g6.POPULATION_HASH,
                frozen_history_sha256=selected['source']['sha256']))
        self.ledger_path.touch(exist_ok=True)
        self.observation_path=root/(FILE_STEM+'_observations.json')
        self.observations=json.loads(self.observation_path.read_text()) if self.observation_path.exists() else {}
        self._atomic_json(self.observation_path,self.observations)

    def _write_status(self):
        super()._write_status()
        row=json.loads(self.status_path.read_text())
        row.update(generation=6,population=400,population_hash=g6.POPULATION_HASH,
                   rule_version=g6.RULE_VERSION,execution_model=self.EXECUTION_MODEL,
                   known_births=len(getattr(self,'births',{})),paper_only=True,
                   daily_equal_start_equity=5000.,max_position_fraction=.2,
                   historical_backfill_enabled=False)
        self._atomic_json(self.status_path,row)

    def _recover_rows(self,handle):
        def observed():
            for line in handle:
                try:
                    r=json.loads(line)
                    if r.get('event_type')=='PAPER_ENTRY' and r.get('strategy_id') in self.IDS:
                        self._last_admitted[r['strategy_id']]=_utc(r['entry_timestamp'])
                    if r.get('event_type') in {'PAPER_ENTRY','PAPER_PARTIAL_EXIT','PAPER_EXIT'} and r.get('strategy_id') in self.IDS:
                        sid=r['strategy_id']
                        if sid not in self._verified_births or _utc(r['signal_timestamp'])<_utc(self._verified_births[sid]):
                            raise ValueError('prebirth G6 fill in ledger')
                except (ValueError,KeyError,TypeError) as exc:
                    raise ValueError('G6 corrupt fill ledger; provenance review required') from exc
                yield line
        super()._recover_rows(observed())
    def _append(self,row):
        event=row.get('event_type')
        q=getattr(self,'_entry_quote_context',None) if event=='PAPER_ENTRY' else getattr(self,'_exit_quotes',{}).get(row.get('symbol'))
        if q is not None and event in {'PAPER_ENTRY','PAPER_PARTIAL_EXIT','PAPER_EXIT'}:
            row['execution_evidence']={k:q.get(k) for k in ('bid','ask','bid_size_raw','ask_size_raw','bid_size','ask_size',
                'bid_time_ms','ask_time_ms','quote_time_ms','collector_observed_at','realtime')}
        super()._append(row)
        if row.get('event_type')=='PAPER_ENTRY':self._last_admitted[row['strategy_id']]=_utc(row['entry_timestamp'])

    def register_signal(self,signal,quote,now):
        sid=signal.get('strategy_id')
        if sid not in self.IDS:return False
        s=g6.spec_for(sid);row=dict(signal);ask=g6.num((quote or {}).get('ask'))
        # Own canonical identity; never let a supplied parent setup dedupe siblings.
        ts=g6.timestamp(row.get('timestamp'))
        if ts is not None:
            row['source_setup_id']=row.get('setup_id')
            row['setup_id']=f"{sid}|{row.get('symbol')}|{ts.replace(second=0,microsecond=0).isoformat()}"
        stop=s.stop;target=s.target_pct
        if ask>0:
            original=g6.num(row.get('original_target_price'))
            row.update(confirmation_reference_price=row.get('entry_price'),stop_price=ask*(1-stop),
                       target_price=(ask+(original-ask)*s.target_scale if sid in g6.IDS else ask*(1+target/100)))
        self._entry_quote_context=dict(quote or {})
        try:return super().register_signal(row,quote,now)
        finally:self._entry_quote_context=None

    def entry_gate(self,signal,quote,now):
        sid=signal['strategy_id'];s=g6.spec_for(sid)
        if signal.get('paper_only') is not True or signal.get('live_order_placement') is not False:
            return 'g6_paper_only_contract'
        if any(signal.get(k)!=v for k,v in [('rule_version',g6.RULE_VERSION),
                 ('population_hash',g6.POPULATION_HASH),('rule_source_sha256',g6.RULE_SOURCE_SHA256)]):
            return 'g6_unknown_frozen_rule'
        t=g6.timestamp(signal.get('timestamp'))
        if t is None:return 'g6_missing_signal_time'
        if sid in g6.MINUTE_IDS:
            if t.second or t.microsecond or g6.timestamp(signal.get('completed_minute'))!=t:
                return 'g6_completed_minute_provenance'
            if signal.get('symbol') not in s.universe:return 'g6_wrong_symbol_cohort'
        else:
            if not g6.raw_accepts(s,signal,12.):return 'g6_raw_admission_failed'
            if not s.min_price<=g6.num(quote.get('ask'))<=s.max_price:return 'g6_price_cohort'
        if not isinstance(signal.get('admission_evidence'),dict) or not signal['admission_evidence']:
            return 'g6_missing_admission_evidence'
        if sid in g6.MINUTE_IDS and not g6.minute_admits(s,signal['admission_evidence']):return 'g6_minute_admission_failed'
        if signal.get('constituent_votes')!=[s.architecture]:return 'g6_wrong_constituent_vote'
        if not g6.time_admits(s,t) or not g6.time_admits(s,now):return 'g6_outside_execution_window'
        last=self._last_admitted.get(sid)
        if last and (now-last).total_seconds()<s.cooldown_seconds:return 'g6_admitted_fill_cooldown'
        for action in ('BUY','SELL'):
            mark=executable_mark(quote,action=action,now=now,max_quote_age_ms=s.max_quote_age_ms)
            if mark['state']!='EXECUTABLE':return mark['reason']
            if mark['quote_age_ms']<0:return 'g6_future_quote'
        return super().entry_gate(signal,quote,now)

    def _available_book(self,sid,symbol,quote,action):
        adjusted,key,identity,used=super()._available_book(sid,symbol,quote,action)
        s=g6.spec_for(sid);side='ask' if action=='BUY' else 'bid'
        now=getattr(self,'_fill_now',None)
        if now is not None:
            mark=executable_mark(quote,action=action,now=now,max_quote_age_ms=s.max_quote_age_ms)
            if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0:
                adjusted[side+'_size_raw']=0
        if s.displayed_participation<1:
            original=g6.num((quote or {}).get(side+'_size_raw',(quote or {}).get(side+'_size')))
            adjusted[side+'_size_raw']=min(g6.num(adjusted.get(side+'_size_raw')),
                                         max(0,math.floor(original*s.displayed_participation)-used))
        return adjusted,key,identity,used

    def quantity_limit(self,sid,signal,ask,cash,requested):
        s=g6.spec_for(sid)
        active=[r for r in self.active.values() if r['strategy_id']==sid]
        equity=cash+sum(r['remaining_qty']*r['entry_price'] for r in active)
        requested=min(requested,math.floor(min(s.notional,equity*s.max_position_fraction,cash)/ask))
        return super().quantity_limit(sid,signal,ask,cash,requested)

    def update_quotes(self,quotes,now):
        now=_utc(now);self._fill_now=now;self._exit_quotes=quotes
        for row in self.active.values():
            if (now-_utc(row['entry_timestamp'])).total_seconds()>=g6.spec_for(row['strategy_id']).max_hold_seconds:
                if not row.get('pending_exit_reason'):row['pending_exit_reason']='G6_MAX_HOLD'
        try:return super().update_quotes(quotes,now)
        finally:self._fill_now=None;self._exit_quotes={}
    def _update_k_checkpoint(self,record,price,now):
        original=record['signal_timestamp']
        try:
            record['signal_timestamp']=record['entry_timestamp']
            return super()._update_k_checkpoint(record,price,now)
        finally:record['signal_timestamp']=original
    def symbols(self,limit=400):
        symbols=sorted(self.by_symbol)
        if not symbols:return set()
        start=self._symbol_cursor%len(symbols);chosen=(symbols[start:]+symbols[:start])[:limit]
        self._symbol_cursor=(start+len(chosen))%len(symbols)
        return set(chosen)

    def observe_snapshot(self,snapshot,*,current,errors=()):
        t=g6.timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond:return
        if self._coverage_last is not None and t<=self._coverage_last:return
        if self._coverage_last is not None and (t-self._coverage_last!=timedelta(minutes=1) or t.astimezone(g6.NY).date()!=self._coverage_last.astimezone(g6.NY).date()):self._coverage.clear()
        self._coverage_last=t
        symbols=set(g6.EQUITIES)|{'SPY'}
        for sym in symbols:
            q=snapshot.quotes.get(sym)
            self._coverage[sym]=min(66,self._coverage[sym]+1) if q and math.isfinite(q.price) and q.price>0 else 0
        if not current:return
        bad={sid for sid,_ in errors};day=t.astimezone(g6.NY).date().isoformat()
        for s in g6.CATALOG:
            sid=s.strategy_id
            if sid not in g6.MINUTE_IDS or t<_utc(self.births[sid]) or not g6.time_admits(s,t):continue
            row=self.observations.setdefault(sid,{}).setdefault(day,dict(evaluated_minutes=0,ready_minutes=0,error_minutes=0,last_minute=None))
            if row['last_minute'] and t<=_utc(row['last_minute']):continue
            needed=set(s.universe)|{'SPY'}
            row.update(last_minute=t.isoformat(),evaluated_minutes=row['evaluated_minutes']+1,
                       error_minutes=row['error_minutes']+int(sid in bad),
                       ready_minutes=row['ready_minutes']+int(sid not in bad and any(self._coverage[x]>=s.lookback+3 for x in s.universe if x!='SPY') and self._coverage['SPY']>=s.lookback+3))
        self._atomic_json(self.observation_path,self.observations)
