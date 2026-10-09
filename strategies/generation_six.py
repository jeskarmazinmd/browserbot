"""G6 evidence-led prospective hypotheses: 50 admission cohorts, eight contrasts.

240 owned raw-flash modules and 160 completed-minute modules. These are paired
experiments, not 400 independent discoveries; no parent-trade subscriptions.
"""
from collections import defaultdict,deque
from dataclasses import asdict,dataclass,replace
from datetime import timedelta
import hashlib,json,math,statistics
from pathlib import Path
from engine.events import SignalEvent
from strategies.generation_three import Experiment as BaseExperiment,NY,EQUITIES
from strategies.generation_two import num,timestamp,parameter_snapshot

SOURCE_COMMIT='cf7b7f77da8325b1647a9d7e9c2776e8e6683a0f'
CREATED_UTC='2026-10-09T21:45:00+00:00'
RULE_VERSION='generation_six_frozen_v1'
EVIDENCE_SHA256='0c2ecaff2bfebb9af1789f69f009e67317e99e5135d41563a4a629f166ea1c9a'
FLASH_ARCHITECTURES=frozenset({'MIDDAY','LOWPRICE','VOL_REVERSAL'})
@dataclass(frozen=True)
class Experiment(BaseExperiment):
 cohort: str=''
 contrast: str=''
 max_quote_age_ms: float=3000.
 displayed_participation: float=.25
 max_hold_seconds: int=900
 min_excess: float=.75
 min_r2: float=.5
 min_short_return: float=.10
 market_floor: float=-.5
 target_min: float=0.
 target_max: float=100000.
 max_rebound_fraction: float=.75
 flash_max_age_seconds: int=300

def time_admits(s,value):
 t=timestamp(value)
 if t is None:return False
 et=t.astimezone(NY)
 return et.weekday()<5 and s.start_minute<=et.hour*60+et.minute<s.end_minute

CONTRASTS={
 'CTL':('Conservative cash, one-symbol and executable-book control',{}),
 'COST':('Tighter contemporaneous cost and liquidity participation',dict(max_quote_age_ms=1000.,max_entry_spread_pct=.05,displayed_participation=.10)),
 'ROOM':('Reject shallow recovery relative to spread',dict(min_target_spread_multiple=8.,min_executable_upside_pct=.75)),
 'FAST':('Cap duration at ten minutes; require positive bid progress at five',dict(max_hold_seconds=600,checkpoint_seconds=300,min_return_pct=0.)),
 'PATIENT':('Allow thirty-minute continuation instead of fifteen',dict(max_hold_seconds=1800)),
 'TARGET':('Take a smaller recovery distance / fixed target',dict(target_scale=.65,target_pct=.60)),
 'PROGRESS':('Require 0.25% bid progress at five minutes',dict(checkpoint_seconds=300,min_return_pct=.25)),
 'RISK':('Quarter nominal stop risk and tighter aggregate risk budget',dict(risk_fraction=.0025,portfolio_risk_fraction=.0075)),
}
_catalog=[]
def add_family(prefix,architecture,source,cohorts,**defaults):
 for i,(hypothesis,changes) in enumerate(cohorts,1):
  cohort=f'G6{prefix}{i:02d}'
  base=Experiment(cohort+'CTL',architecture,source,hypothesis,cohort+'CTL',cohort=cohort,
   risk_fraction=.01,max_position_fraction=.20,portfolio_risk_fraction=.02,
   one_position_per_symbol=True,max_entry_spread_pct=.15,min_price=1.,max_price=100000.,
   cooldown_seconds=600,stop=.02,**defaults)
  base=replace(base,**changes)
  for contrast,(idea,intervention) in CONTRASTS.items():
   _catalog.append(replace(base,strategy_id=cohort+contrast,contrast=contrast,
                  hypothesis=hypothesis+'; '+idea,**intervention))

add_family('M','MIDDAY','PMID+G3MU150+G3MRB20+G3MR260',[
 ('Midday pretrend-shock recovery control',{}),
 ('Require 1.0% pretrend',dict(min_pre_return=1.)),
 ('Require 1.25% pretrend',dict(min_pre_return=1.25)),
 ('Require pretrend fit R2 0.65',dict(min_pre_r2=.65)),
 ('Require pretrend fit R2 0.80',dict(min_pre_r2=.80)),
 ('Require 1.5% shock',dict(min_flash_drop=1.5)),
 ('Require 2% shock',dict(min_flash_drop=2.)),
 ('Require 0.2% observed rebound',dict(rebound_fraction=.002)),
 ('Require 0.3% observed rebound',dict(rebound_fraction=.003)),
 ('Predeclare $5 minimum, without excluding named winners',dict(min_price=5.)),
 ('Predeclare $20 minimum',dict(min_price=20.)),
 ('First midday hour only',dict(start_minute=720,end_minute=780)),
 ('Second midday hour only',dict(start_minute=780,end_minute=840)),
 ('Bound recovered fraction to one-half of shock',dict(max_rebound_fraction=.5)),
 ('Stronger trend and rebound jointly',dict(min_pre_return=1.,min_pre_r2=.65,rebound_fraction=.002)),
],start_minute=720,end_minute=840)
add_family('L','LOWPRICE','PT315PLOW+PT315T75+G2PGK10+G2PGK5+G2PGB1',[
 ('Low-price P recovery control',dict(max_price=5.)),
 ('Exclude sub-$2 without naming symbols',dict(min_price=2.,max_price=5.)),
 ('$3-$5 cohort',dict(min_price=3.,max_price=5.)),
 ('Sub-$3 cohort',dict(max_price=3.)),
 ('Stronger pretrend in low-price recovery',dict(min_pre_return=1.,max_price=5.)),
 ('Smoother pretrend in low-price recovery',dict(min_pre_r2=.7,max_price=5.)),
 ('Larger low-price shock',dict(min_flash_drop=1.5,max_price=5.)),
 ('Larger low-price rebound',dict(rebound_fraction=.002,max_price=5.)),
 ('Morning low-price recovery',dict(start_minute=600,end_minute=720,max_price=5.)),
 ('Afternoon low-price recovery',dict(start_minute=780,end_minute=900,max_price=5.)),
],start_minute=600,end_minute=900,target_min=3.25,target_max=31.5)
add_family('V','VOL_REVERSAL','G3QV425X600+QV4VB608',[
 ('Normalized shock recovery 4.25-6 sigma',dict(min_units=4.25,max_units=6.)),
 ('Normalized shock recovery 6-8 sigma',dict(min_units=6.,max_units=8.)),
 ('Normalized shock recovery with smoother pretrend',dict(min_units=4.25,max_units=8.,min_pre_r2=.65)),
 ('Midday normalized shock recovery',dict(min_units=4.25,max_units=8.,start_minute=720,end_minute=840)),
 ('Normalized recovery with stronger rebound',dict(min_units=4.25,max_units=8.,rebound_fraction=.002)),
],start_minute=600,end_minute=900)
add_family('R','RELATIVE','RS1+RS2',[
 ('Relative-strength control',{}),
 ('Stronger absolute strength',dict(min_return=1.)),
 ('Stronger market-relative edge',dict(min_excess=1.)),
 ('Smoother relative trend',dict(min_r2=.7)),
 ('Fifteen-minute relative trend',dict(lookback=15)),
 ('Forty-five-minute relative trend',dict(lookback=45)),
 ('Strict positive-market cohort',dict(market_floor=0.)),
 ('Morning relative-strength cohort',dict(start_minute=630,end_minute=720)),
 ('Afternoon relative-strength cohort',dict(start_minute=780,end_minute=900)),
 ('Broad funds only relative strength',dict(universe=('QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLY','XLP','XLI','XLU','SMH','IYT'))),
],start_minute=630,end_minute=900,min_return=.75,target_pct=.9)
add_family('P','PULLBACK','RS1+PT315PLOW',[
 ('Strong relative trend, five-minute pullback and one-minute recovery',{}),
 ('Larger relative edge on pullback',dict(min_excess=1.)),
 ('Stronger one-minute resumption',dict(min_short_return=.2)),
 ('Fifteen-minute pullback context',dict(lookback=15)),
 ('Smoother trend before pullback',dict(min_r2=.7)),
],start_minute=630,end_minute=900,min_return=.75,target_pct=.9)
add_family('B','RETEST','RS1+G3MRB20',[
 ('Relative leader retakes prior bounded high after a dip',{}),
 ('Require larger high-break buffer',dict(buffer_pct=.15)),
 ('Require tighter prebreak range',dict(range_pct=.75)),
 ('Forty-five-minute retest context',dict(lookback=45)),
 ('Positive-market retest only',dict(market_floor=0.)),
],start_minute=630,end_minute=900,min_return=.75,target_pct=.9)
CATALOG=tuple(_catalog)
ALL_IDS=frozenset(s.strategy_id for s in CATALOG)
IDS=frozenset(s.strategy_id for s in CATALOG if s.architecture in FLASH_ARCHITECTURES)
MINUTE_IDS=ALL_IDS-IDS
_BY_ID={s.strategy_id:s for s in CATALOG}
assert len(CATALOG)==len(ALL_IDS)==400 and len(IDS)==240 and len(MINUTE_IDS)==160
POPULATION_HASH=hashlib.sha256(json.dumps([asdict(s) for s in CATALOG],sort_keys=True).encode()).hexdigest()
RULE_SOURCE_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def spec_for(sid):return _BY_ID[sid]
def semantic_key(s):
 return json.dumps({k:v for k,v in asdict(s).items() if k not in {'strategy_id','hypothesis','comparison_id','cohort','contrast','source'}},sort_keys=True)
assert len({semantic_key(s) for s in CATALOG})==400

def metadata(sid):
 s=spec_for(sid)
 return dict(strategy_id=sid,generation=6,family='GENERATION_SIX',paper_only=True,
  description=s.hypothesis,source_strategy_ids=s.source.split('+'),source_commit=SOURCE_COMMIT,
  evidence_sha256=EVIDENCE_SHA256,created_utc=CREATED_UTC,comparison_id=s.comparison_id,
  cohort=s.cohort,parameters=parameter_snapshot(asdict(s)),rule_version=RULE_VERSION,
  population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,
  independent_discovery=False,prospective_start_policy='durable first activation; never backfilled',
  universe_definition=('raw scanner equity universe with executable price bounds' if sid in IDS else list(s.universe)),
  config=dict(flash_drop_pct=s.min_flash_drop,rebound_confirmation_pct=s.rebound_fraction,
              pending_rebound_timeout_seconds=s.flash_max_age_seconds,min_remaining_upside_pct=.20,
              stop_loss_fraction=s.stop,live_order_placement=False))
def raw_accepts(s,event,maximum):
 drop=num(event.get('original_flash_drop_pct',event.get('flash_drop_pct')),-1)
 if not s.min_flash_drop<=drop<=maximum:return False
 if s.architecture in {'MIDDAY','LOWPRICE'}:
  if num(event.get('pre_return_pct'),-1e99)<s.min_pre_return or num(event.get('pre_r2'),-1e99)<s.min_pre_r2:return False
 else:
  std=num(event.get('pre30_return_std_pct'))
  if std<=0 or not s.min_units<=drop/std<=s.max_units:return False
  if s.min_pre_r2>.5 and num(event.get('pre_r2'),-1e99)<s.min_pre_r2:return False
 target=num(event.get('original_target_price',event.get('target_price')))
 return s.target_min<=target<=s.target_max

def executable_votes(sid,event,ask,bid):
 s=spec_for(sid)
 if not raw_accepts(s,event,12.) or not time_admits(s,event.get('timestamp')) or not s.min_price<=ask<=s.max_price:return ()
 original=num(event.get('original_target_price'));drop=num(event.get('original_flash_drop_pct',event.get('flash_drop_pct')))
 trough=original*(1-drop/100)
 if trough<=0 or original<=trough or (ask-trough)/(original-trough)>s.max_rebound_fraction:return ()
 return (s.architecture,)

def signal_row(s,price,original,evidence):
 row=dict(entry_price=price,target_price=(price+(original-price)*s.target_scale if s.strategy_id in IDS else price*(1+s.target_pct/100)),
  stop_price=price*(1-s.stop),paper_only=True,live_order_placement=False,forward_start_utc=CREATED_UTC,
  experimental_child=True,research_generation=6,rule_version=RULE_VERSION,rule_source_sha256=RULE_SOURCE_SHA256,
  population_hash=POPULATION_HASH,constituent_votes=[s.architecture],admission_evidence=evidence,research_metadata=metadata(s.strategy_id))
 if s.checkpoint_seconds:row.update(exit_model='k_checkpoint',mode='conditional_return',seconds=s.checkpoint_seconds,min_return_pct=s.min_return_pct)
 else:row['exit_model']='target_stop_eod'
 return row
class FlashModule:
 PAPER_ONLY=True
 def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__='strategies.generation_six.'+sid
 @property
 def CONFIG(self):return metadata(self.STRATEGY_ID)['config']
 def metadata(self):return metadata(self.STRATEGY_ID)
 def accepts_flash(self,event,maximum):return raw_accepts(spec_for(self.STRATEGY_ID),event,maximum)
 def refresh_event_for_entry(self,event,price):
  s=spec_for(self.STRATEGY_ID);original=num(event['target_price']);r=dict(event)
  r.update(signal_row(s,price,original,{k:event.get(k) for k in ('pre_return_pct','pre_r2','flash_drop_pct','pre30_return_std_pct')}))
  r.update(strategy_id=s.strategy_id,original_target_price=original,original_flash_drop_pct=event['flash_drop_pct'],
   remaining_upside_pct=(original/price-1)*100,stop_loss_fraction=s.stop)
  return r
 def validate_confirmed_entry(self,event,minimum):
  s=spec_for(self.STRATEGY_ID);t=timestamp(event.get('timestamp'));price=num(event.get('entry_price'))
  if t is None or t<timestamp(CREATED_UTC) or not time_admits(s,t):return False,'g6_time_window'
  if price<=0 or (num(event.get('target_price'))/price-1)*100<minimum:return False,'g6_target_geometry'
  return (True,None) if raw_accepts(s,event,12.) else (False,'g6_raw_rule')
MODULES={sid:FlashModule(sid) for sid in sorted(IDS)}

def fit_r2(prices):
 logs=[math.log(p) for p in prices];mx=(len(logs)-1)/2;mean=statistics.mean(logs)
 xx=sum((i-mx)**2 for i in range(len(logs)));yy=sum((v-mean)**2 for v in logs)
 xy=sum((i-mx)*(v-mean) for i,v in enumerate(logs))
 return xy*xy/(xx*yy) if xx and yy else 0.
def features(prices,lookback):
 p=list(prices)
 if len(p)<lookback+3:return None
 prior=p[-lookback-1:-1]
 return dict(price=p[-1],ret=(p[-1]/p[-lookback-1]-1)*100,r2=fit_r2(p[-lookback-1:]),
  ret5=(p[-1]/p[-6]-1)*100,ret1=(p[-1]/p[-2]-1)*100,
  prior_high=max(prior),prior_range=(max(prior)/min(prior)-1)*100,
  had_dip=p[-2]<max(p[-6:-2]),breakout=(p[-1]/max(prior)-1)*100)
class FeatureStore:
 """Shared causal market features, never shared portfolio or signal state."""
 def __init__(self):self.history=defaultdict(lambda:deque(maxlen=66));self.last=None;self.snapshot=None;self.cache={}
 def consume(self,snapshot):
  if self.snapshot is snapshot:return self.cache
  t=timestamp(snapshot.timestamp)
  if t is None or t.second or t.microsecond:return {}
  if self.last is not None and t<=self.last:return {}
  if self.last is not None and (t-self.last!=timedelta(minutes=1) or t.astimezone(NY).date()!=self.last.astimezone(NY).date()):self.history.clear()
  self.last=t;self.snapshot=snapshot
  for sym in set(EQUITIES)|{'SPY'}:
   q=snapshot.quotes.get(sym)
   if q is None or not math.isfinite(q.price) or q.price<=0:self.history[sym].clear()
   else:self.history[sym].append(float(q.price))
  self.cache={(sym,n):features(self.history[sym],n) for sym in self.history for n in (15,30,45)}
  return self.cache
_FEATURE_STORE=FeatureStore()
def minute_admits(s,f):
 if not f or any(k not in f or not math.isfinite(num(f[k],float('nan'))) for k in ('ret','r2','ret5','ret1','excess','spy_return','breakout','prior_range')):return False
 ok=f['ret']>=s.min_return and f['excess']>=s.min_excess and f['r2']>=s.min_r2 and f['spy_return']>=s.market_floor
 if s.architecture=='RELATIVE':return ok and f['ret5']>=s.min_short_return
 if s.architecture=='PULLBACK':return ok and -.5<=f['ret5']<0 and f['ret1']>=s.min_short_return
 if s.architecture=='RETEST':return ok and f.get('had_dip') is True and f['breakout']>=s.buffer_pct and f['prior_range']<=s.range_pct
 return False

def candidate(s,fs):
 spy=fs.get(('SPY',s.lookback))
 if not spy:return None
 rows=[]
 for sym in s.universe:
  if sym=='SPY':continue
  f=fs.get((sym,s.lookback))
  if not f:continue
  evidence=dict(f,excess=f['ret']-spy['ret'],spy_return=spy['ret'])
  if minute_admits(s,evidence):rows.append((evidence['excess'],sym,f['price'],evidence))
 return max(rows,default=None,key=lambda r:(r[0],r[1]))
class MinuteStrategy:
 PAPER_ONLY=True
 def __init__(self,sid,store=None):self.name=sid;self.spec=spec_for(sid);self.store=store or _FEATURE_STORE
 def on_snapshot(self,snapshot):
  fs=self.store.consume(snapshot);s=self.spec;t=timestamp(snapshot.timestamp)
  if t is None or t<timestamp(CREATED_UTC) or not time_admits(s,t):return []
  result=candidate(s,fs)
  if result is None:return []
  _,symbol,price,evidence=result;row=signal_row(s,price,price,evidence);row['completed_minute']=t.isoformat()
  return [SignalEvent(t,s.strategy_id,symbol,'SIGNAL',row)]
class MinuteCatalog:
 IDS=MINUTE_IDS
 spec_for=staticmethod(spec_for)
 metadata=staticmethod(metadata)
MINUTE_CATALOG=MinuteCatalog()
for _sid in sorted(MINUTE_IDS):
 def _init(self,sid=_sid):MinuteStrategy.__init__(self,sid)
 globals()[_sid+'Strategy']=type(_sid+'Strategy',(MinuteStrategy,),{'__init__':_init,'__module__':__name__})
