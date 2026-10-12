"""Two isolated G7 paper accounts; immutable provenance and executable fills."""
import hashlib,json
from pathlib import Path
from datetime import timedelta
from collections import defaultdict
from executable_paper_engine import executable_mark
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from paper_outcome_tracker import _utc
from strategies import generation_seven as g
FILE_STEM='paper_generation_seven_bidask_independent'
IDS=g.ALL_IDS
class GenerationSevenBidAskTracker(GenerationTwoBidAskTracker):
 IDS=IDS
 FILE_STEM=FILE_STEM
 flash_catalog=g
 minute_catalog=g
 EXECUTION_MODEL='GENERATION_SEVEN_BIDASK_V1'
 def __init__(self,data_root,**kwargs):
  root=Path(data_root);root.mkdir(parents=True,exist_ok=True)
  manifest=root/(FILE_STEM+'_manifest.json');birth=root/(FILE_STEM+'_births.json');ledger=root/(FILE_STEM+'_outcomes.jsonl')
  frozen=dict(rule_version=g.RULE_VERSION,population_hash=g.POPULATION_HASH,rule_source_sha256=g.RULE_SOURCE_SHA256,parent_sources=g.SOURCE_HASHES,tracker_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
  if manifest.exists() and json.loads(manifest.read_text())!=frozen:raise ValueError('G7 frozen sources changed; use new IDs')
  if (ledger.exists() and ledger.stat().st_size or manifest.exists() or birth.exists()) and (not manifest.exists() or not birth.exists()):raise ValueError('G7 missing provenance; refuse reset')
  self._verified_births=json.loads(birth.read_text()) if birth.exists() else {}
  if birth.exists() and set(self._verified_births)!=IDS:raise ValueError('G7 birth population mismatch')
  self._fill_now=None;self._exit_quotes={};self._entry_quote=None;self._last_admitted={}
  super().__init__(data_root,**kwargs)
  self._atomic_json(manifest,frozen);self.ledger_path.touch(exist_ok=True)
  self.observation_path=root/(FILE_STEM+'_observations.json')
  self.observations=json.loads(self.observation_path.read_text()) if self.observation_path.exists() else {}
  self._atomic_json(self.observation_path,self.observations)
 def _recover_rows(self,handle):
  def verified():
   for line in handle:
    try:
     row=json.loads(line)
     if row.get('strategy_id') not in IDS:raise ValueError('unknown G7 ledger ID')
     if row.get('strategy_id') in IDS and row.get('event_type') in ('PAPER_ENTRY','PAPER_PARTIAL_EXIT','PAPER_EXIT'):
      sid=row['strategy_id']
      if row['event_type']=='PAPER_ENTRY':self._last_admitted[(sid,row['symbol'])]=_utc(row['entry_timestamp'])
      if sid not in self._verified_births or _utc(row['signal_timestamp'])<_utc(self._verified_births[sid]):raise ValueError('prebirth fill')
    except (ValueError,KeyError,TypeError) as exc:raise ValueError('G7 corrupt ledger; review required') from exc
    yield line
  super()._recover_rows(verified())
 def _append(self,row):
  row.update(paper_only=True,broker_execution_enabled=False,live_order_placement=False)
  q=self._entry_quote if row.get('event_type')=='PAPER_ENTRY' else self._exit_quotes.get(row.get('symbol'))
  if q is not None:
   row['execution_evidence']={k:q.get(k) for k in ('bid','ask','bid_size_raw','ask_size_raw','bid_time_ms','ask_time_ms','quote_time_ms','collector_observed_at','realtime')}
  super()._append(row)
  if row.get('event_type')=='PAPER_ENTRY':self._last_admitted[(row['strategy_id'],row['symbol'])]=_utc(row['entry_timestamp'])
 def _write_status(self):
  super()._write_status();r=json.loads(self.status_path.read_text())
  r.update(generation=7,population=len(IDS),population_hash=g.POPULATION_HASH,known_births=len(self.births),paper_only=True,historical_backfill_enabled=False,daily_equal_start_equity=5000.,risk_fraction=.01,max_position_fraction=.2,rule_version=g.RULE_VERSION)
  self._atomic_json(self.status_path,r)
 def register_signal(self,signal,quote,now):
  if signal.get('strategy_id') not in IDS:return False
  row=dict(signal);row['source_setup_id']=row.get('setup_id');row.pop('setup_id',None)
  self._entry_quote=quote
  try:return super().register_signal(row,quote,now)
  finally:self._entry_quote=None
 def entry_gate(self,signal,quote,now):
  if signal.get('paper_only') is not True or signal.get('live_order_placement') is not False:return 'g7_paper_only_contract'
  if any(signal.get(k)!=v for k,v in [('rule_version',g.RULE_VERSION),('population_hash',g.POPULATION_HASH),('rule_source_sha256',g.RULE_SOURCE_SHA256)]):return 'g7_frozen_rule_mismatch'
  t=g.timestamp(signal.get('timestamp'));minute=g.timestamp(signal.get('completed_minute'))
  if t is None or minute is None or minute.second or minute.microsecond or t!=minute+timedelta(minutes=1) or _utc(now)<t:return 'g7_completed_minute_provenance'
  last=self._last_admitted.get((signal['strategy_id'],signal.get('symbol')))
  if last and (_utc(now)-last).total_seconds()<1800:return 'g7_symbol_fill_cooldown'
  s=g._BY_ID[signal['strategy_id']]
  if signal.get('symbol') not in g.POOL or signal.get('constituent_votes')!=[g.PARENTS[s.family][0]]:return 'g7_owned_parent_rule'
  evidence=signal.get('admission_evidence')
  if not isinstance(evidence,dict) or not g.admission_accepts(s.strategy_id,evidence,signal['symbol']):return 'g7_admission_evidence'
  for action in ('BUY','SELL'):
   m=executable_mark(quote,action=action,now=now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:return 'g7_nonexecutable_quote'
  return super().entry_gate(signal,quote,now)
 def _available_book(self,sid,symbol,quote,action):
  adjusted,key,identity,used=super()._available_book(sid,symbol,quote,action)
  if self._fill_now is not None:
   m=executable_mark(quote,action=action,now=self._fill_now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:adjusted[('ask' if action=='BUY' else 'bid')+'_size_raw']=0
  return adjusted,key,identity,used
 def update_quotes(self,quotes,now):
  now=_utc(now)
  quotes={s:q for s,q in quotes.items() if (lambda m:m['state']=='EXECUTABLE' and m.get('quote_age_ms',-1)>=0)(executable_mark(q,action='SELL',now=now,max_quote_age_ms=5000))}
  self._fill_now=now;self._exit_quotes=quotes
  for row in self.active.values():
   if g._BY_ID[row['strategy_id']].mechanism!='PROTECT' or row.get('pending_exit_reason'):continue
   m=executable_mark(quotes.get(row['symbol']),action='SELL',now=now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:continue
   bid=m['price'];high=max(row.get('g7_high_bid',row['entry_price']),bid);row['g7_high_bid']=high;self._dirty=True
   # Original stop/target retain priority. Trailing protection is a request
   # to sell available displayed bids, never a fill at the trailing threshold.
   if row['stop_price']<bid<row['target_price'] and high>=row['entry_price']*1.005 and bid<=high*.9965:row['pending_exit_reason']='G7_PROFIT_PROTECT'
  try:return super().update_quotes(quotes,now)
  finally:self._fill_now=None;self._exit_quotes={}
 def observe_snapshot(self,snapshot,*,current,errors=()):
  if not current:return
  t=_utc(snapshot.timestamp)+timedelta(minutes=1);bad={sid for sid,_ in errors}
  for sid in IDS:
   if t<_utc(self.births[sid]):continue
   day=t.date().isoformat();r=self.observations.setdefault(sid,{}).setdefault(day,dict(evaluated_minutes=0,error_minutes=0,last_minute=None))
   if r['last_minute'] and t<=_utc(r['last_minute']):continue
   r.update(evaluated_minutes=r['evaluated_minutes']+1,error_minutes=r['error_minutes']+int(sid in bad),last_minute=t.isoformat())
  self._atomic_json(self.observation_path,self.observations)
