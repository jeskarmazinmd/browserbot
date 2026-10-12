"""Mechanism hypotheses. Each owns a parent evaluator; never subscribes to signals."""
from dataclasses import dataclass
from importlib import import_module
from collections import deque
from datetime import timedelta
from engine.events import SignalEvent
PARENTS={'ROT':('CMDROT1','strategy_cmdrot1',.0075,1.),'GAS':('CMDGAS1','strategy_cmdgas1',.008,1.),'BRD':('CMDBRD1','strategy_cmdbrd1',.007,.9)}
POOL=('GLD','SLV','GDX','USO','UNG','XLE','XME','COPX','DBA')
@dataclass(frozen=True)
class Hypothesis:
 strategy_id:str
 family:str
 mechanism:str
 description:str
 track:str='A'
RESEARCH_CATALOG=tuple(Hypothesis('G7'+family+mode,family,mode,desc,track) for family,mode,desc,track in [
 ('ROT','CARRY','Leader has positive five-minute and nonnegative one-minute continuation','A'),
 ('ROT','BROAD','Require positive 30-minute commodity breadth of at least 65%','A'),
 ('ROT','REL','Require 30-minute leader excess return over SPY of at least 0.25%','A'),
 ('ROT','STABLE','Require the same commodity leader for three completed minutes','A'),
 ('ROT','PROTECT','After 0.5% bid gain, protect with a 0.35% trailing exit','B'),
 ('GAS','CARRY','Require positive five-minute UNG and nonnegative five-minute XLE','A'),
 ('GAS','REL','Require 15-minute UNG excess return over SPY of at least 0.35%','A'),
 ('GAS','COST','Require executable spread no larger than 0.10%','B'),
 ('GAS','PROTECT','After 0.5% bid gain, protect with a 0.35% trailing exit','B'),
 ('BRD','CARRY','Require positive five-minute leader continuation','A'),
 ('BRD','STABLE','Require 65% positive breadth at both five and fifteen minutes','A'),
 ('BRD','REL','Require 15-minute leader excess return over SPY of at least 0.20%','A'),
 ('BRD','PROTECT','After 0.5% bid gain, protect with a 0.35% trailing exit','B'),
])
def ret(history,symbol,n):
 h=list(history[symbol]);return (h[-1]/h[-n-1]-1)*100 if len(h)>n and h[-n-1]>0 else None
class Evaluator:
 def __init__(self,spec):
  self.spec=spec;self.module=import_module('strategies.'+PARENTS[spec.family][1]);self.parent=self.module.Strategy();self.leaders=deque(maxlen=3);self.last=None
 def on_snapshot(self,snapshot):
  # Variant history is contiguous and exchange-session bounded. Parent controls
  # are separately replayed with their original implementation unchanged.
  if self.last is not None and (snapshot.timestamp-self.last!=timedelta(minutes=1) or snapshot.timestamp.date()!=self.last.date()):
   self.parent=self.module.Strategy();self.leaders.clear()
  if self.last is not None and snapshot.timestamp<=self.last:return []
  self.last=snapshot.timestamp
  # Missing observations must never compress elapsed minutes into a lookback.
  for s in self.module.UNIVERSE:
   if s not in snapshot.quotes:self.parent._h[s].clear()
  events=self.parent.on_snapshot(snapshot);h=self.parent._h
  n=self.module.PARAMS['lookback'];values={s:ret(h,s,n) for s in POOL};ready={s:v for s,v in values.items() if v is not None}
  leader=max(ready,key=lambda s:(ready[s],s)) if ready else None;self.leaders.append(leader)
  result=[]
  for e in events:
   r5=ret(h,e.symbol,5);r1=ret(h,e.symbol,1);market=ret(h,'SPY',n);excess=ret(h,e.symbol,n)-market if market is not None and ret(h,e.symbol,n) is not None else None
   breadth=sum(v>0 for v in ready.values())/len(ready) if len(ready)>=5 else None
   v5={s:ret(h,s,5) for s in POOL};v5={s:v for s,v in v5.items() if v is not None};b5=sum(v>0 for v in v5.values())/len(v5) if len(v5)>=5 else None
   mode=self.spec.mechanism;ok=False
   if mode=='CARRY':ok=r5 is not None and r5>0 and (self.spec.family=='BRD' or (r1 is not None and r1>=0))
   if mode=='CARRY' and self.spec.family=='GAS':ok=r5 is not None and r5>0 and ret(h,'XLE',5) is not None and ret(h,'XLE',5)>=0
   if mode=='BROAD':ok=breadth is not None and breadth>=.65
   if mode=='REL':ok=excess is not None and excess>={'ROT':.25,'GAS':.35,'BRD':.20}[self.spec.family]
   if mode=='STABLE':ok=(len(self.leaders)==3 and all(s==e.symbol for s in self.leaders)) if self.spec.family=='ROT' else (breadth is not None and b5 is not None and breadth>=.65 and b5>=.65)
   if mode in ('COST','PROTECT'):ok=True
   if ok:
    data=dict(e.data,admission_evidence=dict(ret5=r5,ret1=r1,excess=excess,breadth=breadth,breadth5=b5,leaders=list(self.leaders),parent_evidence=e.data.get('research')),source_setup_id=e.data.get('setup_id'),paper_only=True,live_order_placement=False,completed_minute=e.timestamp.isoformat(),rule_version=RULE_VERSION,population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,constituent_votes=[PARENTS[self.spec.family][0]],forward_start_utc=CREATED_UTC,research_metadata=metadata(self.spec.strategy_id) if self.spec.strategy_id in ALL_IDS else {"research_only":True},experimental_child=True,research_generation=7)
    result.append(SignalEvent(e.timestamp+timedelta(minutes=1),self.spec.strategy_id,e.symbol,e.signal_type,data))
  return result


# Two mechanism experiments survived opportunity-retention review. Historical
# replay is development evidence; acceptance is for prospective paper testing.
SELECTED=('G7ROTPROTECT','G7BRDSTABLE')
CATALOG=tuple(s for s in RESEARCH_CATALOG if s.strategy_id in SELECTED)
ALL_IDS=frozenset(SELECTED)
IDS=frozenset()  # No raw flash subscriptions or broker routes.
MINUTE_IDS=ALL_IDS
SOURCE_COMMIT='01ad5a62cc2d026a362b490ef30d6f5a982be580'
CREATED_UTC='2026-10-12T17:00:00+00:00'
RULE_VERSION='generation_seven_frozen_v1'
from pathlib import Path
import hashlib,json,math
from dataclasses import asdict
from strategies.generation_two import num,timestamp,parameter_snapshot
@dataclass(frozen=True)
class ExecutionSpec:
 strategy_id:str
 votes:int=1
 notional:float=1000.
 equity:float=5000.
 risk_fraction:float=.01
 max_position_fraction:float=.2
 portfolio_risk_fraction:float|None=None
 one_position_per_symbol:bool=False
 max_entry_spread_pct:float=math.inf
 min_executable_upside_pct:float=0.
 min_target_spread_multiple:float=0.
_BY_ID={s.strategy_id:s for s in CATALOG}
def spec_for(sid):return ExecutionSpec(sid)
SOURCE_HASHES={name:hashlib.sha256(Path(__file__).with_name(name+'.py').read_bytes()).hexdigest() for name in ('strategy_cmdrot1','strategy_cmdbrd1')}
POPULATION_HASH=hashlib.sha256(json.dumps([asdict(s) for s in CATALOG],sort_keys=True).encode()).hexdigest()
RULE_SOURCE_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def metadata(sid):
 s=_BY_ID[sid]
 return dict(strategy_id=sid,generation=7,family='GENERATION_SEVEN',paper_only=True,
  source_strategy_ids=[PARENTS[s.family][0]],source_commit=SOURCE_COMMIT,
  created_utc=CREATED_UTC,hypothesis=s.description,research_track=s.track,
  parameters=parameter_snapshot(asdict(spec_for(sid))),mechanism=s.mechanism,
  rule_version=RULE_VERSION,population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,
  parent_source_hashes=SOURCE_HASHES,independent_discovery=False,
  prospective_start_policy='durable first activation; never backfilled',
  config=dict(live_order_placement=False),universe=list(POOL),
  evidence_policy='minute-archive development; future prospective sessions are independent test')
def admission_accepts(sid,evidence,symbol):
 s=_BY_ID[sid];p=evidence.get('parent_evidence') or {}
 if s.family=='ROT':
  if num(p.get('best_return'),-math.inf)<.6:return False
 elif num(p.get('best_return'),-math.inf)<.25 or num(p.get('breadth'),-math.inf)<.65:return False
 if s.mechanism=='CARRY':return num(evidence.get('ret5'),-math.inf)>0 and num(evidence.get('ret1'),-math.inf)>=0
 if s.mechanism=='STABLE':
  if s.family=='ROT':return len(evidence.get('leaders',[]))==3 and all(x==symbol for x in evidence['leaders'])
  return num(evidence.get('breadth'),-math.inf)>=.65 and num(evidence.get('breadth5'),-math.inf)>=.65
 return s.mechanism=='PROTECT'
class Strategy(Evaluator):
 PAPER_ONLY=True
 def __init__(self,sid):
  self.name=sid;super().__init__(_BY_ID[sid])
for _sid in sorted(ALL_IDS):
 def _init(self,sid=_sid):Strategy.__init__(self,sid)
 globals()[_sid+'Strategy']=type(_sid+'Strategy',(Strategy,),{'__init__':_init,'__module__':__name__})
