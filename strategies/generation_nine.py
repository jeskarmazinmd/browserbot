"""400 frozen STHEDGE2 experiments; aligned causal history, no broker API.

Features are shared for efficiency. State, admissions, cash and outcomes remain
independent per strategy. Every catalog entry has a distinct executable rule.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import statistics
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
RULE_VERSION = 'G9_STHEDGE2_V1'
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False


@dataclass(frozen=True)
class Spec:
    strategy_id: str = ''
    family: str = ''
    hypothesis: str = ''
    short_window: int = 30
    long_window: int = 100
    residual_window: int = 60
    recent_window: int = 10
    beta_drift: float = .25
    beta_min: float = .2
    beta_max: float = 2.5
    entry_z: float = 2.
    cooldown_minutes: int = 30
    target_pct: float = .45
    stop_pct: float = .38
    max_hold_minutes: int = 120
    hedge_scale: float = 1.
    direction: str = 'BOTH'
    universe: str = 'ALL'
    first_minute: int = 575
    last_minute: int = 930
    max_spread_bps: float = 100.
    min_sd_bps: float = 0.
    max_sd_bps: float = 1e6
    market_filter: str = 'ANY'
    require_turn: bool = False
    exit_z: float = -1.
    gross_notional: float = 1000.
    participation: float = 1.
    slippage_bps: float = 0.
    borrow_bps_annual: float = 300.


def _catalog():
    rows = []
    def family(name, reason, changes):
        assert len(changes) == 20
        for i, change in enumerate(changes, 1):
            rows.append(replace(Spec(), strategy_id=f'G9{name}{i:02d}', family=name,
                                hypothesis=reason, **change))
    family('Z', 'Select residual dislocations of different strength; first is exact parent signal threshold.',
           [dict(entry_z=v) for v in [2.,1.4,1.5,1.6,1.7,1.8,1.9,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,3.,3.2,3.4,3.6,4.]])
    family('DRIFT', 'Tighter hedge stability may reduce false mean reversion.',
           [dict(beta_drift=round(.025+i*.025,3)) for i in range(21) if round(.025+i*.025,3)!=.25])
    family('SHORT', 'Change hedge adaptation speed while retaining the long estimate.',
           [dict(short_window=v) for v in range(15,55,2)])
    family('LONG', 'Change equilibrium estimation horizon.',
           [dict(long_window=v) for v in [x for x in range(65,170,5) if x!=100]])
    family('RECENT', 'Change residual accumulation horizon and its variance normalization.',
           [dict(recent_window=v) for v in [x for x in range(3,24) if x!=10]])
    family('RESID', 'Change residual volatility estimation horizon.',
           [dict(residual_window=v) for v in [x for x in range(30,135,5) if x!=60]])
    family('COOL', 'Test admission frequency with a single concurrent group.',
           [dict(cooldown_minutes=v) for v in [x for x in range(5,110,5) if x!=30]])
    family('TARGET', 'Take profits at different grouped net return levels.',
           [dict(target_pct=round(.1+i*.05,3)) for i in range(21) if round(.1+i*.05,3)!=.45])
    family('STOP', 'Limit failed convergence at different grouped net losses.',
           [dict(stop_pct=round(.1+i*.03,3)) for i in range(20)])
    family('HOLD', 'Test convergence speed and capital lockup.',
           [dict(max_hold_minutes=v) for v in [x for x in range(10,220,10) if x!=120]])
    family('HEDGE', 'Test under/over hedging; measure residual market exposure.',
           [dict(hedge_scale=round(.5+i*.05,3)) for i in range(21) if round(.5+i*.05,3)!=1.])
    family('BETA', 'Restrict to distinct stable-beta cohorts.',
           [dict(beta_min=lo,beta_max=hi) for lo in [.1,.3,.5,.7,.9] for hi in [1.2,1.6,2.,3.]])
    family('SIDE', 'Separate residual signs and threshold interactions.',
           [dict(direction=d,entry_z=z) for d in ['LONG','SHORT'] for z in [1.5,1.7,1.9,2.1,2.3,2.5,2.7,3.,3.3,3.6]])
    family('COHORT', 'Separate stock, sector ETF, macro ETF, and index behavior.',
           [dict(universe=u,entry_z=z) for u in ['STOCK','SECTOR','MACRO','INDEX'] for z in [1.5,1.75,2.,2.25,2.5]])
    family('SESSION', 'Separate intraday regimes without optimizing historical dates.',
           [dict(first_minute=a,last_minute=b,entry_z=z) for a,b in [(575,690),(630,810),(690,900),(780,930)] for z in [1.5,1.75,2.,2.25,2.5]])
    family('COST', 'Reject spreads that are large relative to plausible convergence.',
           [dict(max_spread_bps=v) for v in range(2,42,2)])
    family('VOL', 'Reject noise-dominated or shock-dominated residuals.',
           [dict(min_sd_bps=lo,max_sd_bps=hi) for lo in [0.,1.,2.,3.] for hi in [5.,10.,15.,25.,40.]])
    family('REGIME', 'Test market direction and confirmation of a residual reversal.',
           [dict(market_filter=m,require_turn=t,entry_z=z) for m in ['UP','DOWN'] for t in [False,True] for z in [1.5,1.75,2.,2.5,3.]])
    family('CONVERGE', 'Exit on observed signal convergence as well as cash risk limits.',
           [dict(exit_z=e,max_hold_minutes=h) for e in [0.,.25,.5,.75,1.] for h in [30,60,90,150]])
    family('ROBUST', 'Predeclared interactions: stable hedge, costs, patience and execution stress.',
           [dict(beta_drift=d,entry_z=z,require_turn=True,max_spread_bps=15.,
                 max_hold_minutes=h,slippage_bps=slip,participation=.5)
            for d,z in [(.1,1.75),(.15,2.),(.2,2.25),(.3,2.5),(.4,2.75)]
            for h,slip in [(60,0.),(90,1.),(120,2.),(180,3.)]])
    return tuple(rows)


CATALOG = _catalog()
SPECS = {s.strategy_id:s for s in CATALOG}
IDS = frozenset(SPECS)
POPULATION_HASH = hashlib.sha256(json.dumps([asdict(s) for s in CATALOG],sort_keys=True).encode()).hexdigest()
assert len(IDS) == 400
assert len({json.dumps({k:v for k,v in asdict(s).items() if k not in {'strategy_id','family','hypothesis'}},sort_keys=True) for s in CATALOG}) == 400


def utc(x):
    t = x if isinstance(x,datetime) else datetime.fromisoformat(str(x).replace('Z','+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timezone required')
    return t.astimezone(timezone.utc)


def finite(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):
        return None


def valid_quote(q,now,max_age=5.):
    b,a=finite(q.get('bid')),finite(q.get('ask'))
    if b is None or a is None or b<=0 or a<b or q.get('realtime') is not True:
        return False
    for side in ['bid','ask']:
        t=finite(q.get(side+'_time_ms',q.get('quote_time_ms')))
        if t is None or not 0<=now.timestamp()-t/1000<=max_age:
            return False
    return True


def beta(a,b):
    ma,mb=statistics.fmean(a),statistics.fmean(b)
    den=sum((v-mb)**2 for v in b)
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/den if den else 0.


STOCKS=frozenset('NVDA AMD AVGO MSFT AAPL GOOGL META AMZN TSLA NFLX ORCL CRM MU INTC JPM BAC GS WMT'.split())
SECTORS=frozenset('XLK XLF XLE XLV XLY XLP XLI XLU XLC SMH IYT'.split())
MACRO=frozenset('GLD SLV USO TLT'.split())
INDEX=frozenset('QQQ IWM DIA'.split())
COHORTS={'STOCK':STOCKS,'SECTOR':SECTORS,'MACRO':MACRO,'INDEX':INDEX}


class Population:
    def __init__(self):
        self.hist=defaultdict(lambda:deque(maxlen=170))
        self.last_minute=None
        self.current={}
        self._cache={}

    def observe(self,timestamp,quotes):
        now=utc(timestamp);minute=now.replace(second=0,microsecond=0)
        if self.last_minute is not None and minute<=self.last_minute:
            return False
        if self.last_minute is not None and ((minute-self.last_minute).total_seconds()!=60 or minute.astimezone(NY).date()!=self.last_minute.astimezone(NY).date()):
            self.hist.clear()
        usable={s:q for s,q in quotes.items() if valid_quote(q,now)}
        # One synchronized row per minute; a missing leg breaks its own sequence.
        for s in set(self.hist)|set(usable):
            if s not in usable:
                self.hist[s].clear()
            else:
                self.hist[s].append((float(usable[s]['bid'])+float(usable[s]['ask']))/2)
        self.last_minute=minute;self.current=usable;self._cache={}
        return True

    def feature(self,spec,symbol):
        key=(symbol,spec.short_window,spec.long_window,spec.residual_window,spec.recent_window)
        if key in self._cache:return self._cache[key]
        n=max(spec.short_window,spec.long_window,spec.residual_window,spec.recent_window)
        a,b=list(self.hist[symbol]),list(self.hist['SPY'])
        if min(len(a),len(b))<n+1:
            self._cache[key]=None;return None
        ar=[(y/x-1)*100 for x,y in zip(a[:-1],a[1:])]
        br=[(y/x-1)*100 for x,y in zip(b[:-1],b[1:])]
        short=beta(ar[-spec.short_window:],br[-spec.short_window:])
        long=beta(ar[-spec.long_window:],br[-spec.long_window:])
        residual=[u-long*v for u,v in zip(ar[-spec.residual_window:],br[-spec.residual_window:])]
        sd=statistics.pstdev(residual)
        recent=sum(residual[-spec.recent_window:])
        z=recent/(sd*math.sqrt(spec.recent_window)) if sd else 0.
        f=dict(long_beta=long,short_beta=short,beta_drift=abs(short-long),residual_z=z,
               residual_sd_bps=sd*100,market_return=sum(br[-spec.recent_window:]),last_residual=residual[-1])
        self._cache[key]=f;return f

    def decision(self,spec,now):
        et=utc(now).astimezone(NY);minute=et.hour*60+et.minute
        if et.weekday()>4 or not spec.first_minute<=minute<spec.last_minute or 'SPY' not in self.current:return None
        best=None
        for symbol,q in sorted(self.current.items()):
            if symbol=='SPY' or (spec.universe!='ALL' and symbol not in COHORTS[spec.universe]):continue
            f=self.feature(spec,symbol)
            if not f or not spec.beta_min<=f['long_beta']<=spec.beta_max or f['beta_drift']>spec.beta_drift:continue
            z=f['residual_z'];side='SHORT' if z>0 else 'LONG'
            if abs(z)<spec.entry_z or (spec.direction!='BOTH' and side!=spec.direction):continue
            if not spec.min_sd_bps<=f['residual_sd_bps']<=spec.max_sd_bps:continue
            if spec.require_turn and z*f['last_residual']>=0:continue
            if spec.market_filter=='UP' and f['market_return']<=0:continue
            if spec.market_filter=='DOWN' and f['market_return']>=0:continue
            if any((float(x['ask'])/float(x['bid'])-1)*10000>spec.max_spread_bps for x in [q,self.current['SPY']]):continue
            if best is None or abs(z)>abs(best['research']['residual_z']):
                best=dict(strategy_id=spec.strategy_id,timestamp=utc(now).isoformat(),research=f,
                          legs=[dict(symbol=symbol,side=side,weight=1.),
                                dict(symbol='SPY',side='LONG' if side=='SHORT' else 'SHORT',weight=f['long_beta']*spec.hedge_scale)],
                          paper_only=True,live_order_placement=False,population_hash=POPULATION_HASH)
        return best
