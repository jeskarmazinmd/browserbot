"""Frozen G3 research population. Explicit opt-in; no broker order capability.

Own raw admission and bounded minute history. Source labels are provenance,
never subscriptions to another strategy's signals or parameter dictionaries.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
import math
from zoneinfo import ZoneInfo
from engine.events import SignalEvent
from strategies.generation_two import num, timestamp, parameter_snapshot

SOURCE_COMMIT = '4c66d144f2de28bef8b80b46208186f66455e045'
CREATED_UTC = '2026-10-06T20:40:00+00:00'
NY = ZoneInfo('America/New_York')
EQUITIES = ('SPY','QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLY','XLP','XLI','XLU','SMH','IYT','GLD','SLV','USO','TLT','NVDA','AMD','AVGO','MSFT','AAPL','GOOGL','META','AMZN','TSLA','NFLX','ORCL','CRM','MU','INTC')
COMMODITIES = ('GLD','SLV','GDX','USO','UNG','XLE','XME','COPX','DBA')

@dataclass(frozen=True)
class Experiment:
    strategy_id: str
    architecture: str
    source: str
    hypothesis: str
    comparison_id: str
    votes: int = 1
    notional: float = 1000.0
    equity: float = 5000.0
    risk_fraction: float | None = None
    max_position_fraction: float = .20
    portfolio_risk_fraction: float | None = None
    one_position_per_symbol: bool = False
    max_entry_spread_pct: float = math.inf
    min_executable_upside_pct: float = .20
    min_target_spread_multiple: float = 0.0
    min_price: float = 0.0
    max_price: float = math.inf
    min_flash_drop: float = 1.0
    min_pre_return: float = .75
    min_pre_r2: float = .50
    min_units: float = 4.25
    max_units: float = 8.0
    rebound_fraction: float = .001
    start_minute: int = 570
    end_minute: int = 955
    stop: float = .05
    target_pct: float = .90
    target_scale: float = 1.0
    checkpoint_seconds: int = 0
    checkpoint_mode: str = 'conditional_return'
    required_gain_pct: float = .25
    min_return_pct: float = 0.0
    cooldown_seconds: int = 0
    lookback: int = 30
    min_return: float = .60
    ret5: float = .25
    up_fraction: float = .58
    breadth: float = .65
    range_pct: float = 1.5
    buffer_pct: float = .08
    secondary_return: float = .10
    universe: tuple[str,...] = EQUITIES

_catalog=[]
def family(prefix, architecture, source, **defaults):
    base=Experiment(prefix+'CTL',architecture,source,'Frozen source predicate; standardized G3 execution',prefix+'CTL',**defaults)
    _catalog.append(base)
    def add(suffix,hypothesis,**changes):
        _catalog.append(replace(base,strategy_id=prefix+suffix,hypothesis=hypothesis,**changes))
    return add

m=family('G3M','MIDDAY','PMID',start_minute=720,end_minute=840)
for v in (.05,.10,.20,.30):m('S'+str(round(v*100)),f'ASK/BID spread <= {v}%',max_entry_spread_pct=v)
for v in (.5,.75,1.,1.5):m('U'+str(round(v*100)),f'Executable target upside >= {v}%',min_executable_upside_pct=v)
for v in (3.,5.,20.):m('P'+str(int(v)),f'Executable price >= ${v:g}',min_price=v)
for v in (1.,1.25,1.5):m('PR'+str(round(v*100)),f'Pre-flash return >= {v}%',min_pre_return=v)
for v in (.6,.7,.8):m('R2'+str(round(v*100)),f'Pre-flash trend R2 >= {v}',min_pre_r2=v)
for v in (.0015,.002,.003):m('RB'+str(round(v*10000)),f'Rebound >= {v*100:g}%',rebound_fraction=v)
for label,a,b in [('H12',720,780),('H13',780,840),('W1130',690,810),('W1230',750,870)]:m(label,'Predeclared adjacent time cohort',start_minute=a,end_minute=b)
for v in (.01,.02,.03,.04):m('D'+str(round(v*100)),f'{v*100:g}% ASK-anchored disaster stop',stop=v)
for v in (300,600,900,1800):m('K'+str(v//60),f'Exit if BID return <=0 at {v//60}m from actual fill',checkpoint_seconds=v)
for v in (.5,.65,.75):m('T'+str(round(v*100)),f'{v*100:g}% remaining recovery target',target_scale=v)
m('ONE','One residual position per symbol',one_position_per_symbol=True)
m('CD10','Ten-minute cooldown after admitted fill',cooldown_seconds=600)
for v in (.001,.0025,.005):m('R'+str(round(v*10000)),f'{v*100:g}% equity nominal stop risk, 20% order cap',risk_fraction=v)
for label,changes in [('Q1',dict(max_entry_spread_pct=.10,min_executable_upside_pct=.75)),('Q2',dict(max_entry_spread_pct=.20,min_executable_upside_pct=1.)),('L1',dict(min_price=5.,stop=.02)),('L2',dict(stop=.02,checkpoint_seconds=600))]:m(label,'Predeclared two-mechanism interaction',**changes)
for v in (1.25,1.5,2.):m('F'+str(round(v*100)),f'Flash decline >= {v}%',min_flash_drop=v)

q=family('G3Q','VOL_REVERSAL','QV4XU1S50V8',max_entry_spread_pct=.50,min_executable_upside_pct=1.)
for v in (.10,.20,.30):q('S'+str(round(v*100)),f'Spread <= {v}%',max_entry_spread_pct=v)
for v in (1.25,1.5,2.):q('U'+str(round(v*100)),f'Executable upside >= {v}%',min_executable_upside_pct=v)
for v in (.02,.03,.04):q('D'+str(round(v*100)),f'{v*100:g}% disaster stop',stop=v)
for lo,hi in [(4.25,6.),(6.,8.),(4.25,10.)]:q('V'+str(round(lo*100))+'X'+str(round(hi*100)),'Predeclared volatility-unit cohort',min_units=lo,max_units=hi)
q('H12','Midday volatility-reversal cohort',start_minute=720,end_minute=840)
q('LATE','Afternoon volatility-reversal cohort',start_minute=840,end_minute=930)
q('ONE','One residual position per symbol',one_position_per_symbol=True)
q('Q1','Tighter spread with reduced stop',max_entry_spread_pct=.20,stop=.03)
q('Q2','Higher edge with a ten-minute progress check',min_executable_upside_pct=1.5,checkpoint_seconds=600)

c=family('G3C','ROTATION','CMDROT1',universe=COMMODITIES,stop=.0075,target_pct=1.,cooldown_seconds=1200)
for v in (15,20,45,60):c('LB'+str(v),f'{v} contiguous completed minutes lookback',lookback=v)
for v in (.4,.8,1.):c('E'+str(round(v*100)),f'Leader return >= {v}%',min_return=v)
for v in (.6,.8,1.2):c('T'+str(round(v*100)),f'ASK-anchored target {v}%',target_pct=v)
for v in (.005,.006,.01):c('D'+str(round(v*10000)),f'{v*100:g}% disaster stop',stop=v)
for v in (600,1800,2400):c('CD'+str(v//60),f'{v//60}m admitted-fill cooldown',cooldown_seconds=v)
for v in (.03,.05,.10):c('S'+str(round(v*100)),f'Executable spread <= {v}%',max_entry_spread_pct=v)
for v in (.0025,.005):c('R'+str(round(v*10000)),f'Nominal stop risk {v*100:g}% equity',risk_fraction=v)
for label,pool in [('METAL',('GLD','SLV','GDX','XME','COPX')),('ENERGY',('USO','UNG','XLE','OIH')),('DIVERS',('GLD','USO','XLE','DBA','TLT','UUP'))]:c(label,'Predeclared sector cohort; no hindsight symbol selection',universe=pool)
for i,changes in enumerate([dict(max_entry_spread_pct=.05,cooldown_seconds=1800),dict(min_return=.8,lookback=20),dict(stop=.006,target_pct=.8),dict(one_position_per_symbol=True,cooldown_seconds=1800),dict(risk_fraction=.005,portfolio_risk_fraction=.015)],1):c('X'+str(i),'Predeclared mechanism interaction',**changes)

cb=family('G3CB','BREADTH','CMDBRD1',universe=COMMODITIES,lookback=15,min_return=.25,stop=.007,target_pct=.9,cooldown_seconds=1200)
for v in (10,20,30):cb('LB'+str(v),f'{v}m breadth lookback',lookback=v)
for v in (.55,.75,.85):cb('B'+str(round(v*100)),f'Positive-return fraction >= {v}',breadth=v)
for v in (.75,1.25):cb('T'+str(round(v*100)),f'{v}% target',target_pct=v)
for v in (.005,.01):cb('D'+str(round(v*10000)),f'{v*100:g}% stop',stop=v)
cb('S5','Spread <=0.05%',max_entry_spread_pct=.05)

cg=family('G3CG','GAS_CONFIRM','CMDGAS1',universe=('UNG','XLE'),lookback=15,min_return=.55,stop=.008,target_pct=1.,cooldown_seconds=1200)
for v in (10,30):cg('LB'+str(v),f'{v}m aligned UNG/XLE confirmation',lookback=v)
for v in (.4,.75):cg('E'+str(round(v*100)),f'UNG return >={v}%',min_return=v)
cg('S10','Spread <=0.1%',max_entry_spread_pct=.10)

t=family('G3T','TREND','TRENDX2',min_return=1.2,stop=.0065,target_pct=.9)
for v in (.9,1.5,1.8):t('E'+str(round(v*100)),f'30m return >={v}%',min_return=v)
for v in (.15,.35,.5):t('F'+str(round(v*100)),f'5m return >={v}%',ret5=v)
for v in (.55,.65,.70):t('UP'+str(round(v*100)),f'Positive minute fraction >={v}',up_fraction=v)
for v in (.6,.75,1.2):t('T'+str(round(v*100)),f'{v}% target',target_pct=v)
for v in (.004,.005,.008):t('D'+str(round(v*10000)),f'{v*100:g}% stop',stop=v)
for v in (300,600):t('CD'+str(v//60),f'{v//60}m admitted-fill cooldown',cooldown_seconds=v)
for v in (.05,.10):t('S'+str(round(v*100)),f'Spread <={v}%',max_entry_spread_pct=v)
for v in (.0025,.005):t('R'+str(round(v*10000)),f'Nominal stop risk {v*100:g}%',risk_fraction=v)
t('ONECD','No symbol stacking plus five-minute cooldown',one_position_per_symbol=True,cooldown_seconds=300)
t('LOWCOST','Spread gate plus ten-minute cooldown',max_entry_spread_pct=.05,cooldown_seconds=600)

b=family('G3B','BREAKOUT','COMPX2',stop=.0055,target_pct=.75,buffer_pct=.08)
for v in (15,20,45):b('LB'+str(v),f'{v}m bounded breakout',lookback=v)
for v in (.05,.10,.15):b('B'+str(round(v*100)),f'{v}% breakout buffer',buffer_pct=v)
for v in (1.,2.):b('W'+str(round(v*100)),f'Prior range <={v}%',range_pct=v)
b('S5','Spread <=0.05%',max_entry_spread_pct=.05)
b('CD10','Ten-minute admitted-fill cooldown',cooldown_seconds=600)
b('ONECD','No symbol stacking and cooldown',one_position_per_symbol=True,cooldown_seconds=600)

CATALOG=tuple(_catalog)
ALL_IDS=frozenset(s.strategy_id for s in CATALOG)
IDS=frozenset(s.strategy_id for s in CATALOG if s.architecture in {'MIDDAY','VOL_REVERSAL'})
MINUTE_IDS=ALL_IDS-IDS
assert len(CATALOG)==len(ALL_IDS)==150
_BY_ID={s.strategy_id:s for s in CATALOG}

def spec_for(sid):return _BY_ID[sid]

def metadata(sid):
    s=spec_for(sid)
    return {'strategy_id':sid,'description':s.hypothesis,'family':'GENERATION_THREE',
            'paper_only':True,'generation':3,'source_strategy_ids':[s.source],
            'created_utc':CREATED_UTC,'source_commit':SOURCE_COMMIT,
            'comparison_id':s.comparison_id,'parameters':parameter_snapshot(asdict(s)),
            'prospective_start_policy':'durable first activation; no historical backfill',
            'execution_anchor':'actual ASK; progress clock begins at actual fill',
            'config':{'flash_drop_pct':s.min_flash_drop,'rebound_confirmation_pct':s.rebound_fraction,
                      'pending_rebound_timeout_seconds':600,'min_remaining_upside_pct':.20,
                      'stop_loss_fraction':s.stop,'live_order_placement':False}}

def raw_accepts(s,event,maximum):
    drop=num(event.get('original_flash_drop_pct',event.get('flash_drop_pct')),-1)
    if not s.min_flash_drop<=drop<=maximum:return False
    if s.architecture=='MIDDAY':
        return num(event.get('pre_return_pct'),-1e99)>=s.min_pre_return and num(event.get('pre_r2'),-1e99)>=s.min_pre_r2
    std=num(event.get('pre30_return_std_pct'))
    return std>0 and s.min_units<=drop/std<=s.max_units

def time_admits(s,value):
    ts=timestamp(value)
    if ts is None:return False
    et=ts.astimezone(NY)
    return et.weekday()<5 and s.start_minute<=et.hour*60+et.minute<s.end_minute

def executable_votes(sid,event,ask,bid):
    s=spec_for(sid)
    if not raw_accepts(s,event,12.) or not time_admits(s,event.get('timestamp')):return ()
    if not s.min_price<=ask<=s.max_price:return ()
    return (s.source,)

class FlashModule:
    PAPER_ONLY=True
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__='strategies.generation_three.'+sid
    @property
    def CONFIG(self):return metadata(self.STRATEGY_ID)['config']
    def metadata(self):return metadata(self.STRATEGY_ID)
    def accepts_flash(self,event,maximum):return raw_accepts(spec_for(self.STRATEGY_ID),event,maximum)
    def refresh_event_for_entry(self,event,price):
        s=spec_for(self.STRATEGY_ID);row=dict(event);original=float(event['target_price'])
        row.update(strategy_id=s.strategy_id,entry_price=price,original_target_price=original,
                   original_flash_drop_pct=event['flash_drop_pct'],target_price=price+(original-price)*s.target_scale,
                   stop_price=price*(1-s.stop),stop_loss_fraction=s.stop,
                   remaining_upside_pct=(original/price-1)*100,paper_only=True,live_order_placement=False,
                   forward_start_utc=CREATED_UTC,experimental_child=True,research_generation=3,
                   rule_version='generation_three_frozen_v1',research_metadata=metadata(s.strategy_id))
        return exit_policy(row,s)
    def validate_confirmed_entry(self,event,minimum):
        s=spec_for(self.STRATEGY_ID);ts=timestamp(event.get('timestamp'))
        if ts is None or ts<timestamp(CREATED_UTC):return False,'before_prospective_start'
        if not time_admits(s,ts):return False,'outside_g3_time_window'
        price=num(event.get('entry_price'));target=num(event.get('target_price'))
        if price<=0 or target<=price:return False,'invalid_target_geometry'
        if (target/price-1)*100<.20:return False,'insufficient_remaining_upside'
        return (True,None) if raw_accepts(s,event,12.) else (False,'raw_rule_failed')

def exit_policy(row,s):
    if s.checkpoint_seconds:
        row.update(exit_model='k_checkpoint',mode=s.checkpoint_mode,seconds=s.checkpoint_seconds,
                   min_return_pct=s.min_return_pct,required_gain_pct=s.required_gain_pct)
    else:row['exit_model']='target_stop_eod'
    return row

MODULES={sid:FlashModule(sid) for sid in sorted(IDS)}

def minute_predicate(s,history):
    rows=[]
    for symbol in s.universe:
        prices=list(history[symbol])
        if len(prices)<s.lookback+1:continue
        ret=(prices[-1]/prices[-s.lookback-1]-1)*100
        if s.architecture=='TREND':
            r5=(prices[-1]/prices[-6]-1)*100
            up=sum(y>x for x,y in zip(prices[-31:],prices[-30:]))/30
            if ret>=s.min_return and r5>=s.ret5 and up>=s.up_fraction:rows.append((r5,symbol,prices[-1],{'ret30':ret,'ret5':r5,'up_fraction':up}))
        elif s.architecture=='BREAKOUT':
            prior=prices[-s.lookback-1:-1];hi,lo=max(prior),min(prior)
            width=(hi/lo-1)*100;excess=(prices[-1]/hi-1)*100
            if width<=s.range_pct and excess+1e-12>=s.buffer_pct:rows.append((excess,symbol,prices[-1],{'prior_range_pct':width,'breakout_pct':excess}))
        else:rows.append((ret,symbol,prices[-1],{'lookback_return':ret}))
    if s.architecture in {'TREND','BREAKOUT'}:return max(rows,default=None,key=lambda r:(r[0],r[1]))
    if s.architecture=='GAS_CONFIRM':
        by_symbol={r[1]:r for r in rows}
        a,b=by_symbol.get('UNG'),by_symbol.get('XLE')
        return a if a and b and a[0]>=s.min_return and b[0]>=s.secondary_return else None
    if len(rows)<min(4,len(s.universe)):return None
    best=max(rows,key=lambda r:(r[0],r[1]))
    if best[0]<s.min_return:return None
    if s.architecture=='BREADTH' and (len(rows)<5 or sum(r[0]>0 for r in rows)/len(rows)<s.breadth):return None
    return best

class MinuteStrategy:
    PAPER_ONLY=True
    def __init__(self,sid):
        self.name=sid;self.spec=spec_for(sid)
        self._history=defaultdict(lambda:deque(maxlen=66));self._last={}
        self._last_snapshot=None
    def on_snapshot(self,snapshot):
        ts=timestamp(snapshot.timestamp)
        if ts is None:return []
        s=self.spec
        # Input must identify the completed minute, not an in-progress observation.
        if ts.second or ts.microsecond:return []
        if self._last_snapshot is not None and ts<=self._last_snapshot:return []
        self._last_snapshot=ts
        for symbol in s.universe:
            last=self._last.get(symbol);quote=snapshot.quotes.get(symbol)
            if last is not None and ts<=last:continue
            if last is not None and (ts-last!=timedelta(minutes=1) or ts.astimezone(NY).date()!=last.astimezone(NY).date()):self._history[symbol].clear()
            if quote is None or not math.isfinite(quote.price) or quote.price<=0:
                self._history[symbol].clear();self._last[symbol]=ts;continue
            self._history[symbol].append(float(quote.price));self._last[symbol]=ts
        if ts<timestamp(CREATED_UTC) or not time_admits(s,ts):return []
        # Cross-symbol predicates use only histories ending at this minute.
        aligned={symbol:self._history[symbol] if self._last.get(symbol)==ts else () for symbol in s.universe}
        result=minute_predicate(s,aligned)
        if not result:return []
        score,symbol,price,metrics=result
        row={'entry_price':price,'target_price':price*(1+s.target_pct/100),
             'stop_price':price*(1-s.stop),'paper_only':True,'live_order_placement':False,
             'forward_start_utc':CREATED_UTC,'experimental_child':True,'research_generation':3,
             'rule_version':'generation_three_frozen_v1','research_metadata':metadata(s.strategy_id),
             'constituent_votes':[s.source],'completed_minute':ts.isoformat(),**metrics}
        return [SignalEvent(ts,s.strategy_id,symbol,'SIGNAL',exit_policy(row,s))]

class MinuteCatalog:
    IDS=MINUTE_IDS
    spec_for=staticmethod(spec_for)
    metadata=staticmethod(metadata)

MINUTE_CATALOG=MinuteCatalog()

class MinuteModule:
    PAPER_ONLY=True
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__='strategies.generation_three.'+sid
    CONFIG={'live_order_placement':False}
    def metadata(self):return metadata(self.STRATEGY_ID)

MINUTE_MODULES={sid:MinuteModule(sid) for sid in sorted(MINUTE_IDS)}

# Stable classes support worker subprocess reconstruction without closures.
for _sid in sorted(MINUTE_IDS):
    def _init(self, sid=_sid):MinuteStrategy.__init__(self,sid)
    globals()[_sid+'Strategy']=type(_sid+'Strategy',(MinuteStrategy,),{'__init__':_init,'__module__':__name__})
