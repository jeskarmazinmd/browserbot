"""G4 isolated portfolios: durable observed ASK entries/BID partial exits."""
from datetime import timedelta
import json
from collections import defaultdict
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from strategies import generation_four as g4
from paper_outcome_tracker import _utc

FILE_STEM='paper_generation_four_bidask_independent'
IDS=g4.ALL_IDS

class GenerationFourBidAskTracker(GenerationTwoBidAskTracker):
    IDS=IDS
    FILE_STEM=FILE_STEM
    flash_catalog=g4
    minute_catalog=g4.MINUTE_CATALOG
    EXECUTION_MODEL='GENERATION_FOUR_BIDASK_V1'

    def __init__(self,*args,**kwargs):
        self._last_admitted={}; self._symbol_cursor=0
        super().__init__(*args,**kwargs)
        self.manifest_path=self.root/(self.FILE_STEM+"_manifest.json")
        frozen=dict(rule_version=g4.RULE_VERSION,population_hash=g4.POPULATION_HASH,
                    rule_source_sha256=g4.RULE_SOURCE_SHA256,population=len(self.IDS))
        if self.manifest_path.exists():
            if json.loads(self.manifest_path.read_text())!=frozen:
                raise ValueError('G4 frozen rule manifest changed; use new experiment IDs for new rules')
        elif self.ledger_path.exists() and self.ledger_path.stat().st_size:
            raise ValueError('G4 ledger exists without frozen manifest; provenance review required')
        else:self._atomic_json(self.manifest_path,frozen)
        self.observation_path=self.root/(self.FILE_STEM+"_observations.json")
        self.observations=json.loads(self.observation_path.read_text()) if self.observation_path.exists() else {}
        self._coverage_last=None; self._coverage=defaultdict(int)

    def _write_status(self):
        super()._write_status()
        status=json.loads(self.status_path.read_text())
        status.update(generation=4,population=len(self.IDS),population_hash=g4.POPULATION_HASH,
                      rule_version=g4.RULE_VERSION,execution_model=self.EXECUTION_MODEL,
                      broker_execution_enabled=False,notional_per_signal=1000.,
                      daily_equal_start_equity=5000.,max_hold_seconds=1200,
                      known_births=len(getattr(self,'births',{})))
        self._atomic_json(self.status_path,status)

    def observe_snapshot(self,snapshot,*,current,errors=()):
        """Verified evaluation opportunities, separate from zero-PnL days.

        Warmup/replay never counts. Missing data, process errors and late
        snapshots cannot become evidence of a failed strategy.
        """
        ts=g4.timestamp(snapshot.timestamp)
        if ts is None or ts.second or ts.microsecond: return
        if self._coverage_last is not None and ts<=self._coverage_last: return
        if self._coverage_last is not None and (ts-self._coverage_last!=timedelta(minutes=1) or ts.astimezone(g4.NY).date()!=self._coverage_last.astimezone(g4.NY).date()): self._coverage.clear()
        self._coverage_last=ts
        symbols={x for s in g4.CATALOG for x in (s.benchmark,)+s.universe}
        for symbol in symbols:
            q=snapshot.quotes.get(symbol)
            self._coverage[symbol]=min(66,self._coverage[symbol]+1) if q and g4.num(q.price)>0 else 0
        if not current: return
        bad={sid for sid,_ in errors}; day=ts.astimezone(g4.NY).date().isoformat()
        for s in g4.CATALOG:
            sid=s.strategy_id
            if ts<_utc(self.births[sid]) or not g4.time_admits(s,ts): continue
            row=self.observations.setdefault(sid,{}).setdefault(day,{'evaluated_minutes':0,'ready_minutes':0,'error_minutes':0,'last_minute':None})
            if row['last_minute'] and ts<=_utc(row['last_minute']): continue
            row['last_minute']=ts.isoformat()
            row['evaluated_minutes']+=1
            row['error_minutes']+=int(sid in bad)
            if sid not in bad and min(self._coverage[x] for x in (s.benchmark,)+s.universe)==66:
                row['ready_minutes']+=1
        self._atomic_json(self.observation_path,self.observations)

    def _recover_rows(self,handle):
        def observed():
            import json
            for line in handle:
                try:
                    row=json.loads(line)
                    if row.get('event_type')=='PAPER_ENTRY' and row.get('strategy_id') in self.IDS:
                        self._last_admitted[row['strategy_id']]=_utc(row['entry_timestamp'])
                except (ValueError,TypeError,KeyError): pass
                yield line
        super()._recover_rows(observed())

    def _append(self,row):
        super()._append(row)
        if row.get('event_type')=='PAPER_ENTRY':
            self._last_admitted[row['strategy_id']]=_utc(row['entry_timestamp'])

    def register_signal(self,signal,quote,now):
        sid=signal.get('strategy_id')
        if sid not in self.IDS: return False
        s=g4.spec_for(sid); row=dict(signal); ask=g4.num((quote or {}).get('ask'))
        # Fixed stop and target anchored to the observed execution ASK.
        if ask>0:
            row.update(confirmation_reference_price=row.get('entry_price'),
                       stop_price=ask*(1-s.stop),target_price=ask*(1+s.target_pct/100))
        return super().register_signal(row,quote,now)

    def entry_gate(self,signal,quote,now):
        s=g4.spec_for(signal['strategy_id'])
        if signal.get('paper_only') is not True or signal.get('live_order_placement') is not False:
            return 'g4_missing_paper_only_contract'
        if (signal.get('rule_version')!=g4.RULE_VERSION or signal.get('population_hash')!=g4.POPULATION_HASH
                or signal.get('rule_source_sha256')!=g4.RULE_SOURCE_SHA256):
            return 'g4_unknown_frozen_rule'
        ts=g4.timestamp(signal.get('timestamp')); completed=g4.timestamp(signal.get('completed_minute'))
        if ts is None or completed!=ts or ts.second or ts.microsecond:
            return 'g4_missing_completed_minute_provenance'
        if signal.get('symbol') not in s.universe or signal.get('constituent_votes')!=[s.mechanism]:
            return 'g4_wrong_cohort_or_mechanism'
        if not isinstance(signal.get('admission_evidence'),dict) or not signal['admission_evidence']:
            return 'g4_missing_admission_evidence'
        if not g4.time_admits(s,ts) or not g4.time_admits(s,now): return 'g4_outside_time_window'
        admitted=self._last_admitted.get(s.strategy_id)
        if admitted is not None and (now-admitted).total_seconds()<s.cooldown_seconds:
            return 'g4_admitted_fill_cooldown'
        return super().entry_gate(signal,quote,now)

    def symbols(self,limit=400):
        symbols=sorted(self.by_symbol)
        if not symbols: return set()
        start=self._symbol_cursor%len(symbols)
        chosen=(symbols[start:]+symbols[:start])[:limit]
        self._symbol_cursor=(start+len(chosen))%len(symbols)
        return set(chosen)

    def update_quotes(self,quotes,now):
        now=_utc(now)
        for row in self.active.values():
            if now-_utc(row['entry_timestamp'])>=timedelta(seconds=g4.spec_for(row['strategy_id']).max_hold_seconds):
                row.setdefault('pending_exit_reason','G4_MAX_HOLD')
                if not row.get('pending_exit_reason'): row['pending_exit_reason']='G4_MAX_HOLD'
        return super().update_quotes(quotes,now)
