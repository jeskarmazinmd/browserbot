"""G5: evidence-led, frozen prospective admissions and mechanism contrasts.

No subscriptions to parent signals. Twelve admissions are crossed with eight
predeclared interventions, not optimized on historical returns. Related rows
are paired experiments, not 96 independent discoveries.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo
from engine.events import SignalEvent
from strategies.generation_two import num, timestamp, parameter_snapshot

SOURCE_COMMIT = 'b947057'
CREATED_UTC = '2026-10-07T20:33:00+00:00'
RULE_VERSION = 'generation_five_frozen_v1'
NY = ZoneInfo('America/New_York')
COMMODITIES = ('GLD','SLV','GDX','USO','UNG','XLE','XME','COPX','DBA')
EQUITIES = ('SPY','QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLY','XLP','XLI','XLU','SMH','IYT','GLD','SLV','USO','TLT','NVDA','AMD','AVGO','MSFT','AAPL','GOOGL','META','AMZN','TSLA','NFLX','ORCL','CRM','MU','INTC')
PROXIES = {'NVDA':'SMH','AMD':'SMH','AVGO':'SMH','MU':'SMH','INTC':'SMH',
           'MSFT':'XLK','AAPL':'XLK','ORCL':'XLK','CRM':'XLK',
           'AMZN':'XLY','TSLA':'XLY','GOOGL':'QQQ','META':'QQQ','NFLX':'QQQ'}
HYPOTHESES = {
 'ROT': ('CMDROT1', 'Thirty-minute commodity leadership persists', COMMODITIES),
 'BRD': ('CMDBRD1', 'Fifteen-minute broad commodity strength supports the leader', COMMODITIES),
 'RB': ('CMDROT1+CMDBRD1', 'Independent leadership and breadth must agree', COMMODITIES),
 'GAS': ('CMDGAS1', 'UNG strength with XLE confirmation persists; narrow mandate', ('UNG','XLE')),
 'TR': ('TRENDX2', 'Smooth thirty-minute strength with five-minute continuation persists', EQUITIES),
 'SIMPLE': ('TRENDX2', 'Thirty-minute strength alone suffices; ablate smoothness and short momentum', EQUITIES),
 'SECTOR': ('TRENDX2', 'Stock continuation requires its contemporaneous sector to agree', tuple(PROXIES)),
 'BREAK': ('TRENDX2+BRK20', 'Trend and bounded-consolidation breakout must independently agree', EQUITIES),
 'PULL': ('TRENDX2', 'Brief pullback and one-minute recovery preserve a longer trend', EQUITIES),
 'CLOSE': ('CLOSEMOM1', 'Late-session strength continues into the close', EQUITIES),
 'QR': ('QV4XU1S50V8', 'Volatility-normalized shock recovery transfers to liquid bounded symbols; exploratory', EQUITIES),
 'MR': ('PMID', 'Midday pretrend shock recovery transfers to liquid bounded symbols; exploratory', EQUITIES),
}
CONTRASTS = {
 'CTL': 'Owned admission with standardized executable cash and book accounting',
 'EXEC': 'Both sides <=1s old, spread <=0.05%, and at most 10% of each displayed side',
 'ROOM': 'Target must exceed eight contemporaneous spreads; price distance is not expected profit',
 'TIME': 'Exit after fifteen minutes from actual fill; executable residuals remain open',
 'PROG': 'Exit if BID return is nonpositive at ten minutes from actual fill',
 'VOL': 'Stop and target scale with lagged minute volatility, using bounded risk geometry',
 'RISK': 'Reduce nominal per-order stop risk from 1% to 0.25% of cost equity',
 'DIVER': 'One residual position per symbol plus at least ten minutes between admitted fills',
}
@dataclass(frozen=True)
class Experiment:
    strategy_id: str
    mechanism: str
    contrast: str
    source: str
    hypothesis: str
    comparison_id: str
    universe: tuple
    votes: int = 1
    notional: float = 1000.
    equity: float = 5000.
    risk_fraction: float = .01
    max_position_fraction: float = .20
    portfolio_risk_fraction: float | None = None
    one_position_per_symbol: bool = False
    max_entry_spread_pct: float = .20
    min_executable_upside_pct: float = .20
    min_target_spread_multiple: float = 0.
    stop: float = .0065
    target_pct: float = .9
    cooldown_seconds: int = 300
    max_hold_seconds: int = 3600
    max_quote_age_ms: float = 5000.
    displayed_participation: float = 1.
    checkpoint_seconds: int = 0
    start_minute: int = 630
    end_minute: int = 945

_catalog=[]
for mechanism,(source,idea,universe) in HYPOTHESES.items():
    changes={}
    if mechanism in {'ROT','RB','GAS','BRD'}:
        changes.update(stop=.0075,target_pct=1.,cooldown_seconds=1200)
    if mechanism=='BRD': changes.update(stop=.007,target_pct=.9)
    if mechanism=='GAS': changes.update(stop=.008,target_pct=1.)
    if mechanism in {'QR','MR'}:
        changes.update(stop=.02,target_pct=1.,cooldown_seconds=600)
    if mechanism=='MR':changes.update(start_minute=720,end_minute=840)
    if mechanism=='CLOSE':changes.update(start_minute=870,end_minute=930,stop=.006,target_pct=.75)
    if mechanism=='SECTOR':changes.update(votes=2)
    if mechanism in {'RB','BREAK'}:changes.update(votes=2)
    base=Experiment('G5'+mechanism+'CTL',mechanism,'CTL',source,idea+'; '+CONTRASTS['CTL'],
                    'G5'+mechanism+'CTL',universe,**changes)
    for contrast,text in CONTRASTS.items():
        intervention={}
        if contrast=='EXEC':intervention.update(max_quote_age_ms=1000.,max_entry_spread_pct=.05,displayed_participation=.10)
        if contrast=='ROOM':intervention.update(min_target_spread_multiple=8.)
        if contrast=='TIME':intervention.update(max_hold_seconds=900)
        if contrast=='PROG':intervention.update(checkpoint_seconds=600)
        if contrast=='RISK':intervention.update(risk_fraction=.0025)
        if contrast=='DIVER':intervention.update(one_position_per_symbol=True,cooldown_seconds=max(600,base.cooldown_seconds))
        _catalog.append(replace(base,strategy_id='G5'+mechanism+contrast,contrast=contrast,
                                hypothesis=idea+'; '+text,**intervention))
CATALOG=tuple(_catalog)
ALL_IDS=MINUTE_IDS=frozenset(s.strategy_id for s in CATALOG)
IDS=frozenset()  # No flash-engine subscription or raw replay admissions.
_BY_ID={s.strategy_id:s for s in CATALOG}
assert len(CATALOG)==len(ALL_IDS)==96
POPULATION_HASH=hashlib.sha256(json.dumps([asdict(s) for s in CATALOG],sort_keys=True).encode()).hexdigest()
RULE_SOURCE_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def spec_for(sid):return _BY_ID[sid]
def metadata(sid):
    s=spec_for(sid)
    return dict(strategy_id=sid,description=s.hypothesis,family='GENERATION_FIVE',generation=5,
                paper_only=True,source_strategy_ids=s.source.split('+'),created_utc=CREATED_UTC,
                source_commit=SOURCE_COMMIT,comparison_id=s.comparison_id,
                parameters=parameter_snapshot(asdict(s)),rule_version=RULE_VERSION,
                population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,
                prospective_start_policy='durable first activation; never backfilled',
                independent_discovery=False,config={'live_order_placement':False})
def time_admits(s,value):
    t=timestamp(value)
    if t is None:return False
    et=t.astimezone(NY)
    return et.weekday()<5 and s.start_minute<=et.hour*60+et.minute<s.end_minute

def features(prices):
    p=list(prices)
    if len(p)<35:return None
    r=[(b/a-1)*100 for a,b in zip(p[:-1],p[1:])]
    ret=lambda n:(p[-1]/p[-n-1]-1)*100
    prior=p[-21:-1];pre=p[-35:-4];flash=p[-4:];low=min(flash)
    sd=statistics.pstdev(r[-31:-1])
    mean=statistics.mean(pre);mx=(len(pre)-1)/2
    slope=sum((i-mx)*(v-mean) for i,v in enumerate(pre))/sum((i-mx)**2 for i in range(len(pre)))
    variance=sum((v-mean)**2 for v in pre)
    r2=(slope*slope*sum((i-mx)**2 for i in range(len(pre)))/variance) if variance else 0.
    drop=(flash[0]-low)/flash[0]*100
    pre_sd=statistics.pstdev([(b/a-1)*100 for a,b in zip(pre,pre[1:])])
    return dict(price=p[-1],ret30=ret(30),ret15=ret(15),ret5=ret(5),ret1=ret(1),
                up_fraction=sum(v>0 for v in r[-30:])/30,
                prior_range_pct=(max(prior)/min(prior)-1)*100,
                breakout_pct=(p[-1]/max(prior)-1)*100,
                lagged_std_pct=sd,flash_drop_pct=drop,rebound_pct=(p[-1]/low-1)*100,
                pre_return_pct=(pre[-1]/pre[0]-1)*100,pre_r2=r2,
                pre_std_pct=pre_sd,volatility_units=drop/pre_sd if pre_sd>0 else 0.)

def candidate(s,history):
    needed=set(s.universe)|({'SPY'} if s.mechanism not in {'ROT','BRD','RB','GAS'} else set())
    if s.mechanism=='SECTOR':needed|=set(PROXIES.values())
    fs={sym:features(history.get(sym,())) for sym in needed}
    fs={sym:f for sym,f in fs.items() if f is not None}
    # Every cohort member must have contiguous current-minute observations.
    if any(sym not in fs for sym in needed):return None
    m=s.mechanism;rows=[]
    breadth=sum(fs[x]['ret15']>0 for x in s.universe)/len(s.universe)
    for sym in s.universe:
        f=fs[sym];votes=[m];ok=False;score=f['ret5']
        if m=='ROT':ok=f['ret30']>=.6;score=f['ret30']
        elif m=='BRD':ok=breadth>=.65 and f['ret15']>=.25;score=f['ret15']
        elif m=='RB':ok=f['ret30']>=.6 and breadth>=.65;votes=['LEADERSHIP','BREADTH'];score=f['ret30']
        elif m=='GAS':ok=sym=='UNG' and f['ret15']>=.55 and fs['XLE']['ret15']>=.10
        elif m=='SIMPLE':ok=f['ret30']>=1.2;score=f['ret30']
        elif m=='TR':ok=f['ret30']>=1.2 and f['ret5']>=.25 and f['up_fraction']>=.58
        elif m=='SECTOR':
            proxy=PROXIES[sym];ok=f['ret30']>=.8 and f['ret5']>=.25 and fs[proxy]['ret30']>=.25
            votes=['STOCK_TREND','SECTOR_TREND']
        elif m=='BREAK':
            ok=(f['ret30']>=1.2 and f['ret5']>=.25 and f['up_fraction']>=.58
                and f['prior_range_pct']<=1.5 and f['breakout_pct']>=.10)
            votes=['TREND','BREAKOUT']
        elif m=='PULL':ok=f['ret30']>=.8 and -.5<=f['ret5']<0 and f['ret1']>=.10
        elif m=='CLOSE':ok=f['ret30']>=.75 and f['ret1']>0;score=f['ret30']
        elif m=='QR':ok=f['flash_drop_pct']>=1. and 4.25<=f['volatility_units']<=8. and f['rebound_pct']>=.10
        elif m=='MR':ok=f['flash_drop_pct']>=1. and f['pre_return_pct']>=.75 and f['pre_r2']>=.5 and f['rebound_pct']>=.10
        if ok:
            evidence={**f,'commodity_breadth':breadth}
            if m=='SECTOR':evidence.update(sector_proxy=PROXIES[sym],sector_return_pct=fs[PROXIES[sym]]['ret30'])
            rows.append((score,sym,f['price'],evidence,votes))
    return max(rows,default=None,key=lambda row:(row[0],row[1]))

class MinuteStrategy:
    PAPER_ONLY=True
    def __init__(self,sid):
        self.name=sid;self.spec=spec_for(sid)
        self._history=defaultdict(lambda:deque(maxlen=66));self._last_snapshot=None
    def on_snapshot(self,snapshot):
        t=timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond:return []
        if self._last_snapshot is not None:
            if t<=self._last_snapshot:return []
            if t-self._last_snapshot!=timedelta(minutes=1) or t.astimezone(NY).date()!=self._last_snapshot.astimezone(NY).date():self._history.clear()
        self._last_snapshot=t
        s=self.spec;needed=set(s.universe)
        if s.mechanism=='SECTOR':needed|=set(PROXIES.values())
        if s.mechanism not in {'ROT','BRD','RB','GAS'}:needed.add('SPY')
        for sym in needed:
            q=snapshot.quotes.get(sym)
            if q is None or not math.isfinite(q.price) or q.price<=0:self._history[sym].clear()
            else:self._history[sym].append(float(q.price))
        if t<timestamp(CREATED_UTC) or not time_admits(s,t):return []
        result=candidate(s,self._history)
        if result is None:return []
        _,sym,price,evidence,votes=result
        row=dict(entry_price=price,target_price=price*(1+s.target_pct/100),stop_price=price*(1-s.stop),
                 paper_only=True,live_order_placement=False,forward_start_utc=CREATED_UTC,
                 experimental_child=True,research_generation=5,rule_version=RULE_VERSION,
                 rule_source_sha256=RULE_SOURCE_SHA256,population_hash=POPULATION_HASH,
                 completed_minute=t.isoformat(),constituent_votes=votes,admission_evidence=evidence,
                 research_metadata=metadata(s.strategy_id))
        if s.checkpoint_seconds:
            row.update(exit_model='k_checkpoint',mode='conditional_return',seconds=s.checkpoint_seconds,
                       min_return_pct=0.,required_gain_pct=.25)
        else:row['exit_model']='target_stop_eod'
        return [SignalEvent(t,s.strategy_id,sym,'SIGNAL',row)]
class MinuteCatalog:
    IDS=MINUTE_IDS
    spec_for=staticmethod(spec_for)
    metadata=staticmethod(metadata)
MINUTE_CATALOG=MinuteCatalog()
class MinuteModule:
    PAPER_ONLY=True
    CONFIG={'live_order_placement':False}
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__='strategies.generation_five.'+sid
    def metadata(self):return metadata(self.STRATEGY_ID)
MINUTE_MODULES={sid:MinuteModule(sid) for sid in MINUTE_IDS}
for _sid in sorted(MINUTE_IDS):
    def _init(self,sid=_sid):MinuteStrategy.__init__(self,sid)
    globals()[_sid+'Strategy']=type(_sid+'Strategy',(MinuteStrategy,),{'__init__':_init,'__module__':__name__})
