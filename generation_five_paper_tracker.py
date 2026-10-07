"""G5 isolated actual-fill portfolios; no broker capability or historical credit."""
from collections import defaultdict
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
from executable_paper_engine import executable_mark
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from paper_outcome_tracker import _utc
from strategies import generation_five as g5

FILE_STEM='paper_generation_five_bidask_independent'
IDS=g5.ALL_IDS
class GenerationFiveBidAskTracker(GenerationTwoBidAskTracker):
    IDS=IDS
    FILE_STEM=FILE_STEM
    flash_catalog=g5
    minute_catalog=g5.MINUTE_CATALOG
    EXECUTION_MODEL='GENERATION_FIVE_BIDASK_V1'

    def __init__(self,data_root,**kwargs):
        root=Path(data_root);manifest=root/(FILE_STEM+'_manifest.json');birth=root/(FILE_STEM+'_births.json')
        ledger=root/(FILE_STEM+'_outcomes.jsonl')
        frozen=dict(rule_version=g5.RULE_VERSION,population_hash=g5.POPULATION_HASH,
                    rule_source_sha256=g5.RULE_SOURCE_SHA256,population=96,
                    tracker_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if manifest.exists() and json.loads(manifest.read_text())!=frozen:
            raise ValueError('G5 frozen manifest changed; use new IDs for revised rules')
        if ledger.exists() and ledger.stat().st_size and (not manifest.exists() or not birth.exists()):
            raise ValueError('G5 ledger without manifest/births; refuse to reset provenance')
        if manifest.exists() and not birth.exists():raise ValueError('G5 births missing; refuse to reset provenance')
        self._verified_births=json.loads(birth.read_text()) if birth.exists() else {}
        if birth.exists() and set(self._verified_births)!=self.IDS:
            raise ValueError('G5 birth population mismatch; refuse to invent starts')
        self._last_admitted={};self._symbol_cursor=0;self._coverage_last=None
        self._coverage=defaultdict(int)
        super().__init__(data_root,**kwargs)
        self._atomic_json(manifest,frozen)
        self.observation_path=root/(FILE_STEM+'_observations.json')
        self.observations=json.loads(self.observation_path.read_text()) if self.observation_path.exists() else {}
        self._atomic_json(self.observation_path,self.observations)

    def _write_status(self):
        super()._write_status()
        row=json.loads(self.status_path.read_text())
        row.update(generation=5,population=96,population_hash=g5.POPULATION_HASH,
                   rule_version=g5.RULE_VERSION,execution_model=self.EXECUTION_MODEL,
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
                            raise ValueError('prebirth G5 fill in ledger')
                except (ValueError,KeyError,TypeError) as exc:
                    raise ValueError('G5 corrupt fill ledger; provenance review required') from exc
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
        s=g5.spec_for(sid);row=dict(signal);ask=g5.num((quote or {}).get('ask'))
        stop=s.stop;target=s.target_pct
        if s.contrast=='VOL':
            sd=g5.num((row.get('admission_evidence') or {}).get('lagged_std_pct'))
            if not math.isfinite(sd) or sd<=0:return False
            stop_pct=min(2.,max(.3,1.5*sd*math.sqrt(15)))
            stop=stop_pct/100;target=2*stop_pct
        if ask>0:row.update(confirmation_reference_price=row.get('entry_price'),
                            stop_price=ask*(1-stop),target_price=ask*(1+target/100))
        self._entry_quote_context=dict(quote or {})
        try:return super().register_signal(row,quote,now)
        finally:self._entry_quote_context=None

    def entry_gate(self,signal,quote,now):
        sid=signal['strategy_id'];s=g5.spec_for(sid)
        if signal.get('paper_only') is not True or signal.get('live_order_placement') is not False:
            return 'g5_paper_only_contract'
        if any(signal.get(k)!=v for k,v in [('rule_version',g5.RULE_VERSION),
                 ('population_hash',g5.POPULATION_HASH),('rule_source_sha256',g5.RULE_SOURCE_SHA256)]):
            return 'g5_unknown_frozen_rule'
        t=g5.timestamp(signal.get('timestamp'))
        if t is None or t.second or t.microsecond or g5.timestamp(signal.get('completed_minute'))!=t:
            return 'g5_completed_minute_provenance'
        if signal.get('symbol') not in s.universe or not isinstance(signal.get('admission_evidence'),dict) or not signal['admission_evidence']:
            return 'g5_missing_cohort_evidence'
        votes=signal.get('constituent_votes')
        expected={'RB':['LEADERSHIP','BREADTH'],'SECTOR':['STOCK_TREND','SECTOR_TREND'],
                  'BREAK':['TREND','BREAKOUT']}.get(s.mechanism,[s.mechanism])
        if votes!=expected:return 'g5_wrong_constituent_votes'
        if not g5.time_admits(s,t) or not g5.time_admits(s,now):return 'g5_outside_execution_window'
        last=self._last_admitted.get(sid)
        if last and (now-last).total_seconds()<s.cooldown_seconds:return 'g5_admitted_fill_cooldown'
        for action in ('BUY','SELL'):
            mark=executable_mark(quote,action=action,now=now,max_quote_age_ms=s.max_quote_age_ms)
            if mark['state']!='EXECUTABLE':return mark['reason']
            if mark['quote_age_ms']<0:return 'g5_future_quote'
        return super().entry_gate(signal,quote,now)

    def _available_book(self,sid,symbol,quote,action):
        adjusted,key,identity,used=super()._available_book(sid,symbol,quote,action)
        s=g5.spec_for(sid);side='ask' if action=='BUY' else 'bid'
        now=getattr(self,'_fill_now',None)
        if now is not None:
            mark=executable_mark(quote,action=action,now=now,max_quote_age_ms=s.max_quote_age_ms)
            if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0:
                adjusted[side+'_size_raw']=0
        if s.displayed_participation<1:
            original=g5.num((quote or {}).get(side+'_size_raw',(quote or {}).get(side+'_size')))
            adjusted[side+'_size_raw']=min(g5.num(adjusted.get(side+'_size_raw')),
                                         max(0,math.floor(original*s.displayed_participation)-used))
        return adjusted,key,identity,used

    def quantity_limit(self,sid,signal,ask,cash,requested):
        s=g5.spec_for(sid)
        active=[r for r in self.active.values() if r['strategy_id']==sid]
        equity=cash+sum(r['remaining_qty']*r['entry_price'] for r in active)
        requested=min(requested,math.floor(min(s.notional,equity*s.max_position_fraction,cash)/ask))
        return super().quantity_limit(sid,signal,ask,cash,requested)

    def update_quotes(self,quotes,now):
        now=_utc(now);self._fill_now=now;self._exit_quotes=quotes
        for row in self.active.values():
            if (now-_utc(row['entry_timestamp'])).total_seconds()>=g5.spec_for(row['strategy_id']).max_hold_seconds:
                if not row.get('pending_exit_reason'):row['pending_exit_reason']='G5_MAX_HOLD'
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
        t=g5.timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond:return
        if self._coverage_last is not None and t<=self._coverage_last:return
        if self._coverage_last is not None and (t-self._coverage_last!=timedelta(minutes=1) or t.astimezone(g5.NY).date()!=self._coverage_last.astimezone(g5.NY).date()):self._coverage.clear()
        self._coverage_last=t
        symbols=set(g5.EQUITIES)|set(g5.COMMODITIES)|set(g5.PROXIES.values())
        for sym in symbols:
            q=snapshot.quotes.get(sym)
            self._coverage[sym]=min(35,self._coverage[sym]+1) if q and math.isfinite(q.price) and q.price>0 else 0
        if not current:return
        bad={sid for sid,_ in errors};day=t.astimezone(g5.NY).date().isoformat()
        for s in g5.CATALOG:
            sid=s.strategy_id
            if t<_utc(self.births[sid]) or not g5.time_admits(s,t):continue
            row=self.observations.setdefault(sid,{}).setdefault(day,dict(evaluated_minutes=0,ready_minutes=0,error_minutes=0,last_minute=None))
            if row['last_minute'] and t<=_utc(row['last_minute']):continue
            needed=set(s.universe)
            if s.mechanism=='SECTOR':needed|=set(g5.PROXIES.values())
            if s.mechanism not in {'ROT','BRD','RB','GAS'}:needed.add('SPY')
            row.update(last_minute=t.isoformat(),evaluated_minutes=row['evaluated_minutes']+1,
                       error_minutes=row['error_minutes']+int(sid in bad),
                       ready_minutes=row['ready_minutes']+int(sid not in bad and min(self._coverage[x] for x in needed)>=35))
        self._atomic_json(self.observation_path,self.observations)
