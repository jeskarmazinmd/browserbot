"""Frozen G4 price-path hypotheses; independent, prospective, paper-only.

These are literature-inspired falsifiable adaptations, not paper replications.
No volume, queue, true OHLC, overnight or event-time information is fabricated.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import timedelta
import hashlib
import json
import math
import statistics as st
from zoneinfo import ZoneInfo
from pathlib import Path
from engine.events import SignalEvent
from strategies.generation_two import num, timestamp

SOURCE_COMMIT = '0af3a25a7d98ee64d849c0f39f3060ac0d165b4f'
CREATED_UTC = '2026-10-07T19:28:35+00:00'
RULE_VERSION = 'generation_four_frozen_v1'
RULE_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
NY = ZoneInfo('America/New_York')
# Fixed economic cohorts; no choice based on recent strategy returns.
POOLS = {
    'INDEX': ('SPY', ('QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLI')),
    'TECH': ('QQQ', ('AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO', 'META', 'AMZN', 'GOOGL')),
    'SECTOR': ('SPY', ('XLY', 'XLP', 'XLU', 'XLV', 'XLI', 'XLF', 'XLE', 'SMH')),
}
HYPOTHESES = {
    'RREV': 'Negative five-minute innovation relative to lagged OLS factor fit, followed by recovery',
    'RCONT': 'Positive factor innovation persists; test idiosyncratic continuation against RREV',
    'FAIL': 'Failed downside range auction reclaims the old floor while factor is stable',
    'RETEST': 'Upside range escape subsequently retests and holds the old ceiling',
    'JCONT': 'Concentrated positive price shock continues rather than immediately fading',
    'JFADE': 'Concentrated negative price shock partially recovers without full retracement',
    'SEMIFLIP': 'Downside-dominated realized semivariance switches to upside dominance',
    'DISPCOMP': 'Cross-sectional dispersion compresses while a residual laggard recovers',
    'RECOUPLE': 'Factor correlation breaks down then recouples from below',
    'SERIAL': 'Negative serial dependence changes to positive dependence with positive drift',
    'OCCUPY': 'Price spends most of a window below its starting level then reclaims it',
    'VRSHIFT': 'Nonoverlapping variance ratio switches from anti-persistence to persistence',
}
SOURCES = {
    'residual': 'https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf',
    'intraday': 'https://doi.org/10.1111/j.1540-6261.2010.01573.x',
    'momentum': 'https://doi.org/10.1016/j.jfineco.2018.05.009',
    'leadlag': 'https://arxiv.org/abs/1401.0462',
    'semivariance': 'https://scholar.harvard.edu/files/downside200808.pdf',
    'variance_ratio': 'https://www.nber.org/papers/w2168',
    'liquidity': 'https://www.nber.org/papers/w17653',
    'selection': 'https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf',
}

@dataclass(frozen=True)
class Experiment:
    strategy_id: str
    mechanism: str
    cohort: str
    benchmark: str
    universe: tuple[str, ...]
    hypothesis: str
    votes: int = 1
    notional: float = 1000.0
    equity: float = 5000.0
    risk_fraction: float | None = None
    max_position_fraction: float = .20
    portfolio_risk_fraction: float | None = None
    one_position_per_symbol: bool = True
    max_entry_spread_pct: float = .08
    min_executable_upside_pct: float = .50
    min_target_spread_multiple: float = 5.0
    stop: float = .004
    target_pct: float = .60
    cooldown_seconds: int = 600
    max_hold_seconds: int = 1200
    start_minute: int = 630
    end_minute: int = 945

CATALOG = tuple(Experiment('G4'+mechanism+cohort, mechanism, cohort, benchmark,
                          symbols, hypothesis)
                for mechanism, hypothesis in HYPOTHESES.items()
                for cohort, (benchmark, symbols) in POOLS.items())
ALL_IDS = frozenset(s.strategy_id for s in CATALOG)
# No flash candidates, parent votes or subscriptions to other generations.
IDS = frozenset()
MINUTE_IDS = ALL_IDS
_BY_ID = {s.strategy_id: s for s in CATALOG}
POPULATION_HASH = hashlib.sha256(json.dumps([asdict(s) for s in CATALOG],
                                          sort_keys=True).encode()).hexdigest()

def spec_for(sid): return _BY_ID[sid]

def metadata(sid):
    s = spec_for(sid)
    return dict(strategy_id=sid, description=s.hypothesis, family='GENERATION_FOUR',
                paper_only=True, generation=4, source_commit=SOURCE_COMMIT,
                created_utc=CREATED_UTC, rule_version=RULE_VERSION,
                population_hash=POPULATION_HASH, rule_source_sha256=RULE_SOURCE_SHA256, mechanism=s.mechanism,
                cohort=s.cohort, parameters=asdict(s), literature=SOURCES,
                adaptation='Price-only, long-only directional hypothesis; not a market-neutral replication',
                prospective_start_policy='durable first activation; no replay credit or backfill',
                config={'live_order_placement': False})

def time_admits(s, value):
    ts = timestamp(value)
    if ts is None: return False
    et = ts.astimezone(NY)
    return et.weekday() < 5 and s.start_minute <= et.hour*60+et.minute < s.end_minute

def returns(p): return [100*math.log(b/a) for a,b in zip(p,p[1:])]
def corr(a,b):
    if len(a)!=len(b) or len(a)<3: return 0.0
    ma,mb=st.mean(a),st.mean(b)
    va=sum((x-ma)**2 for x in a); vb=sum((y-mb)**2 for y in b)
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(va*vb) if va*vb>1e-16 else 0.0

def variance_ratio(r):
    # Fixed 3-minute nonoverlapping returns versus one-minute variance.
    v=st.pvariance(r)
    blocks=[sum(r[i:i+3]) for i in range(0,len(r)-2,3)]
    return st.pvariance(blocks)/(3*v) if v>1e-12 and len(blocks)>=5 else None

def feature_rows(s, history):
    b=list(history.get(s.benchmark, ()))
    if len(b)<66: return {}
    br=returns(b[-66:]); train_b=br[:45]
    mb=st.mean(train_b); vb=st.pvariance(train_b)
    if vb<1e-10: return {}
    rows={}
    for symbol in s.universe:
        p=list(history.get(symbol, ()))
        if len(p)<66: continue
        p=p[-66:]; r=returns(p); tr=r[:45]; mt=st.mean(tr)
        beta=sum((x-mb)*(y-mt) for x,y in zip(train_b,tr))/(45*vb)
        if not math.isfinite(beta) or not -.5<=beta<=3: continue
        alpha=mt-beta*mb
        residual=[x-alpha-beta*y for x,y in zip(r,br)]
        sd=st.pstdev(residual[:45]); scale=st.pstdev(tr)
        if scale<.005 or sd<.003: continue
        # The fit ends 20 minutes before the decision. No current-return fit leakage.
        f=dict(p=p,r=r,br=br,beta=beta,alpha=alpha,residual=residual,
               residual_sd=sd,ret5=sum(r[-5:]),ret1=r[-1],factor5=sum(br[-5:]),
               residual5=sum(residual[-5:]),z=sum(residual[-5:])/(sd*math.sqrt(5)),
               prior_corr=corr(r[:45],br[:45]),recent_corr=corr(r[-5:],br[-5:]),
               disrupted_corr=corr(r[-15:-5],br[-15:-5]),train_scale=scale)
        rows[symbol]=f
    return rows

def predicate(s, history):
    rows=feature_rows(s,history)
    # All cohort constituents are required: missing symbols cannot alter ranks/breadth.
    if len(rows)!=len(s.universe): return None
    recent=[f['ret5'] for f in rows.values()]
    prior=[sum(f['r'][-10:-5]) for f in rows.values()]
    dispersion=st.pstdev(recent); prior_dispersion=st.pstdev(prior)
    median=st.median(recent); candidates=[]
    for symbol,f in rows.items():
        p,r,br=f['p'],f['r'],f['br']; ret5=f['ret5']; r1=f['ret1']; z=f['z']
        m=s.mechanism; ok=False; score=0.; extra={}
        if m=='RREV':
            ok=z<=-2 and f['residual5']<=-.15 and r1>.03 and f['factor5']>=-.15
            score=-z
        elif m=='RCONT':
            ok=z>=2 and f['residual5']>=.15 and r1>.03 and f['factor5']>=-.15
            score=z
        elif m=='FAIL':
            floor=min(p[-32:-2]); depth=100*(p[-2]/floor-1); reclaim=100*(p[-1]/floor-1)
            ok=depth<=-.10 and reclaim>=.03 and f['factor5']>=-.15
            score=-depth; extra=dict(floor=floor,depth_pct=depth,reclaim_pct=reclaim)
        elif m=='RETEST':
            ceiling=max(p[-36:-6]); escape=100*(p[-6]/ceiling-1)
            distance=100*(min(p[-5:])/ceiling-1)
            ok=escape>=.10 and 0<=distance<=.12 and r1>.03 and ret5>-.10
            score=escape; extra=dict(ceiling=ceiling,escape_pct=escape,retest_distance_pct=distance)
        elif m in {'JCONT','JFADE'}:
            shock=r[-3]; tail=r[-5:]; rv=sum(x*x for x in tail)
            concentration=shock*shock/rv if rv else 0
            standardized=shock/f['train_scale']
            # Sparse minute returns cannot certify a continuous-time jump.
            if m=='JCONT': ok=standardized>=3 and shock>=.15 and concentration>=.65 and sum(r[-2:])>.03
            else: ok=standardized<=-3 and shock<=-.15 and concentration>=.65 and .03<sum(r[-2:])<abs(shock)*.75
            score=abs(standardized); extra=dict(shock_pct=shock,shock_scale=standardized,concentration=concentration)
        elif m=='SEMIFLIP':
            def upside(xs):
                rv=sum(x*x for x in xs)
                return sum(x*x for x in xs if x>0)/rv if rv>1e-10 else .5
            old,new=upside(r[-20:-5]),upside(r[-5:])
            ok=old<=.25 and new>=.80 and ret5>=.15 and sum(br[-5:])>=0
            score=new-old; extra=dict(old_upside_share=old,new_upside_share=new)
        elif m=='DISPCOMP':
            ok=prior_dispersion>=.20 and dispersion<prior_dispersion*.65 and ret5<median-.10 and r1>.03 and median>=0
            score=median-ret5; extra=dict(dispersion=dispersion,prior_dispersion=prior_dispersion,cohort_median=median)
        elif m=='RECOUPLE':
            ok=f['prior_corr']>=.6 and f['disrupted_corr']<.1 and f['recent_corr']>=.6 and z<=-1.5 and r1>.03 and f['factor5']>0
            score=f['recent_corr']-f['disrupted_corr']
        elif m=='SERIAL':
            old=corr(r[:29],r[1:30]); new=corr(r[-16:-1],r[-15:])
            ok=old<=-.25 and new>=.35 and ret5>=.15
            score=new-old; extra=dict(old_serial=old,new_serial=new)
        elif m=='OCCUPY':
            anchor=p[-21]; occupation=sum(x<anchor for x in p[-20:-1])/19
            ok=occupation>=.85 and p[-2]<anchor and p[-1]>anchor*1.0003 and f['factor5']>=0
            score=occupation; extra=dict(anchor=anchor,underwater_occupation=occupation)
        elif m=='VRSHIFT':
            old=variance_ratio(r[:30]); new=variance_ratio(r[-30:])
            ok=old is not None and new is not None and old<.6 and new>1.4 and ret5>=.15
            score=(new-old) if ok else 0; extra=dict(old_variance_ratio=old,new_variance_ratio=new)
        if ok:
            metrics={k:v for k,v in f.items() if k not in {'p','r','br','residual'}}
            metrics.update(extra, score=score,fit_return_count=45,fit_ends_minutes_before_signal=20,
                           required_cohort_size=len(s.universe))
            candidates.append((score,symbol,p[-1],metrics))
    return max(candidates,default=None,key=lambda x:(x[0],x[1]))

class MinuteStrategy:
    PAPER_ONLY=True
    def __init__(self,sid):
        self.name=sid; self.spec=spec_for(sid)
        self._history=defaultdict(lambda:deque(maxlen=66)); self._last=None
        self.nearest_miss={'state':'WARMUP','required_minutes':66}
    def on_snapshot(self,snapshot):
        ts=timestamp(snapshot.timestamp)
        if ts is None or ts.second or ts.microsecond: return []
        if self._last is not None and ts<=self._last: return []
        et=ts.astimezone(NY)
        if et.weekday()>=5 or not 570<=et.hour*60+et.minute<960:
            self._history.clear(); self._last=ts; return []
        if self._last is not None and (ts-self._last!=timedelta(minutes=1) or et.date()!=self._last.astimezone(NY).date()): self._history.clear()
        self._last=ts
        s=self.spec; pool=(s.benchmark,)+s.universe
        for symbol in pool:
            q=snapshot.quotes.get(symbol)
            price=num(q.price) if q else 0
            if price<=0: self._history[symbol].clear()
            else: self._history[symbol].append(price)
        coverage=min(len(self._history[x]) for x in pool)
        self.nearest_miss={'state':'READY' if coverage==66 else 'WARMUP_OR_GAP',
                           'contiguous_minutes':coverage,'required_minutes':66,
                           'mechanism':s.mechanism,'population_hash':POPULATION_HASH}
        if ts<timestamp(CREATED_UTC) or not time_admits(s,ts): return []
        result=predicate(s,self._history)
        if result is None: return []
        score,symbol,price,metrics=result
        data=dict(entry_price=price,target_price=price*(1+s.target_pct/100),
                  stop_price=price*(1-s.stop),paper_only=True,live_order_placement=False,
                  experimental_child=True,research_generation=4,rule_version=RULE_VERSION,
                  population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,completed_minute=ts.isoformat(),
                  forward_start_utc=CREATED_UTC,constituent_votes=[s.mechanism],
                  research_metadata=metadata(s.strategy_id),admission_evidence=metrics,
                  setup_id=f'{s.strategy_id}|{symbol}|{ts.isoformat()}',exit_model='target_stop_eod')
        return [SignalEvent(ts,s.strategy_id,symbol,'SIGNAL',data)]

class MinuteModule:
    PAPER_ONLY=True
    CONFIG={'live_order_placement':False}
    def __init__(self,sid): self.STRATEGY_ID=sid; self.__name__=__name__+'.'+sid
    def metadata(self): return metadata(self.STRATEGY_ID)
MINUTE_MODULES={sid:MinuteModule(sid) for sid in sorted(MINUTE_IDS)}
class MinuteCatalog:
    IDS=MINUTE_IDS
    spec_for=staticmethod(spec_for)
    metadata=staticmethod(metadata)
MINUTE_CATALOG=MinuteCatalog()
for _sid in sorted(MINUTE_IDS):
    def _init(self,sid=_sid): MinuteStrategy.__init__(self,sid)
    globals()[_sid+'Strategy']=type(_sid+'Strategy',(MinuteStrategy,),{'__init__':_init,'__module__':__name__})
