"""G11: cost-aware long-only experiments from nine frozen selected parents.

Parent evaluators consume market observations, never historical fills or live
parent portfolios. Three G9 parents remain unchanged controls, not duplicated
research seeds: their paired exposures and borrow availability are unresolved.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from functools import lru_cache
import math
import statistics
from engine.events import SignalEvent
from strategies import generation_three as g3, generation_six as g6, generation_seven as g7
from strategies import generation_ten as primitives

NY = g3.NY
num = primitives.num
timestamp = primitives.timestamp
digest = primitives.digest
time_admits = g3.time_admits
CREATED_UTC = '2026-10-20T18:36:34.408334+00:00'
RULE_VERSION = 'G11_NINE_PARENT_LONG_V1'
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
PARENTS = ('G7ROTPROTECT', 'G3CGLB30', 'G6R05TARGET', 'G6R05CTL',
           'G3MPR150', 'G6R05ROOM', 'G6R07CTL', 'G6R06PATIENT', 'G3MT50')
FLASH_PARENTS = frozenset({'G3MPR150', 'G3MT50'})
FAMILY_COUNTS = dict(ENTRY=160, RISK=140, REGIME=120, HOLD=110, COMBO=100, EXEC=92)


def parent_spec(parent):
    if parent.startswith('G3'): return g3.spec_for(parent)
    if parent.startswith('G6'): return g6.spec_for(parent)
    return None


@dataclass(frozen=True)
class Spec(primitives.Spec):
    parent: str = ''
    secondary: str = ''
    mode: str = 'MINUTE'
    market_floor: float = -1e6
    min_symbol_vol: float = 0.
    max_symbol_vol: float = 1e6


def base(parent):
    p = parent_spec(parent)
    changes = dict(parent=parent, mode='FLASH' if parent in FLASH_PARENTS else 'MINUTE',
                   one_position_per_symbol=True, cooldown_seconds=600, max_hold_seconds=3600)
    if p is not None:
        changes.update(stop=p.stop, target_scale=p.target_scale,
                       fixed_target_pct=0. if parent in FLASH_PARENTS else p.target_pct,
                       min_pre_return=p.min_pre_return, min_pre_r2=p.min_pre_r2,
                       start_minute=p.start_minute, end_minute=p.end_minute,
                       cooldown_seconds=p.cooldown_seconds,
                       max_hold_seconds=getattr(p, 'max_hold_seconds', 10800),
                       min_upside_pct=p.min_executable_upside_pct,
                       min_edge_spreads=p.min_target_spread_multiple,
                       checkpoint_seconds=p.checkpoint_seconds,
                       checkpoint_gain_pct=p.min_return_pct)
    else:
        changes.update(stop=.0075, fixed_target_pct=1., trailing_pct=.35,
                       trailing_arm_pct=.5, cooldown_seconds=1800)
    return Spec(**changes)


def _catalog():
    rows = []
    minute = [p for p in PARENTS if p not in FLASH_PARENTS]
    for family, count in FAMILY_COUNTS.items():
        for i in range(count):
            pool = minute if family == 'REGIME' else PARENTS
            parent = pool[i % len(pool)]
            j = i // len(pool)
            s = base(parent)
            secondary = ''
            if family == 'ENTRY':
                changes = dict(start_minute=s.start_minute+2*(j+1),
                               cooldown_seconds=s.cooldown_seconds+60*(j+1))
                hypothesis = f'Delay session admission {2*(j+1)} minutes and extend fill cooldown {j+1} minutes to reduce clustered entries'
            elif family == 'RISK':
                changes = dict(risk_fraction=round(.001+.0004*j, 6),
                               max_position_fraction=round(.05+.009*j, 6))
                hypothesis = f'Nominal risk {changes["risk_fraction"]:.2%} and symbol cap {changes["max_position_fraction"]:.1%} test concentration sensitivity'
            elif family == 'REGIME':
                changes = dict(market_floor=round(-.40+.05*j, 5),
                               max_symbol_vol=round(.12+.025*j, 5))
                hypothesis = f'Require SPY 5-minute return >= {changes["market_floor"]}% and observed symbol minute volatility <= {changes["max_symbol_vol"]}%'
            elif family == 'HOLD':
                changes = dict(max_hold_seconds=180+120*j,
                               stop=round(s.stop*(.50+.035*j), 7))
                hypothesis = f'Limit holding to {changes["max_hold_seconds"]//60} minutes with {changes["stop"]:.3%} executable-price disaster stop'
            elif family == 'COMBO':
                if parent in FLASH_PARENTS:
                    secondary = 'G3MT50' if parent == 'G3MPR150' else 'G3MPR150'
                elif parent.startswith('G6'):
                    secondary = 'G6R07CTL' if parent != 'G6R07CTL' else 'G6R05CTL'
                else:
                    secondary = 'G3CGLB30' if parent != 'G3CGLB30' else 'G7ROTPROTECT'
                other = base(secondary)
                changes = dict(target_scale=(s.target_scale+other.target_scale)/2 * (.60+.025*j),
                               stop=min(s.stop, other.stop),
                               fixed_target_pct=0. if parent in FLASH_PARENTS else
                                   max(s.min_upside_pct+.15, (s.fixed_target_pct+other.fixed_target_pct)/2*(.65+.025*j)),
                               max_hold_seconds=600+60*j)
                hypothesis = f'Require same-observation admission from {parent} and {secondary}; blend exits with predeclared recovery scale {.60+.025*j:.3f}'
            else:
                changes = dict(max_spread_pct=round(.025+.0125*j, 6),
                               participation=round(.05+.025*j, 6),
                               slippage_bps=1.+.5*j, max_quote_age_ms=750+150*j)
                hypothesis = f'Cap spread {changes["max_spread_pct"]}%, book participation {changes["participation"]:.1%}, quote age {changes["max_quote_age_ms"]}ms; stress {changes["slippage_bps"]}bps adverse slippage per side'
            rows.append(replace(s, strategy_id=f'G11{family}{i+1:03d}', family=family,
                                secondary=secondary, hypothesis=hypothesis, **changes))
    return tuple(rows)


CATALOG = _catalog()
ALL_IDS = frozenset(s.strategy_id for s in CATALOG)
IDS = ALL_IDS
FLASH_IDS = frozenset(s.strategy_id for s in CATALOG if s.mode == 'FLASH')
MINUTE_IDS = ALL_IDS-FLASH_IDS
SPECS = {s.strategy_id:s for s in CATALOG}
spec_for = SPECS.__getitem__
POPULATION_HASH = digest([asdict(s) for s in CATALOG])
assert len(CATALOG) == len(ALL_IDS) == 722
assert len({digest({k:v for k,v in asdict(s).items() if k not in {'strategy_id','family','hypothesis'}}) for s in CATALOG}) == 722


@lru_cache(maxsize=722)
def metadata(sid):
    s = SPECS[sid]
    return dict(strategy_id=sid, generation=11, family=s.family,
                parent=s.parent+'BA', parents=[p+'BA' for p in (s.parent,s.secondary) if p],
                hypothesis=s.hypothesis, description=s.hypothesis, parameters=asdict(s),
                config_hash=digest(asdict(s)), population_hash=POPULATION_HASH,
                rule_version=RULE_VERSION, paper_only=True, broker_execution_enabled=False,
                prospective_start_policy='durable first activation; never backfilled',
                config=dict(flash_drop_pct=s.min_flash_drop, rebound_confirmation_pct=s.rebound_fraction,
                            pending_rebound_timeout_seconds=s.pending_timeout,
                            min_remaining_upside_pct=s.min_upside_pct, stop_loss_fraction=s.stop,
                            live_order_placement=False))


def raw_accepts(s,e,maximum=12.):
    if s.mode != 'FLASH':return False
    return all(g3.raw_accepts(parent_spec(p), e, maximum) for p in (s.parent,s.secondary) if p)


def admission(s,e,ask,bid,now):
    ts = timestamp(e.get('timestamp'))
    if ts is None or not time_admits(s,ts) or not time_admits(s,now):return 'time_window'
    if s.mode == 'FLASH':
        if not raw_accepts(s,e):return 'parent_raw_predicate'
        return primitives.admission(s,e,ask,bid,now)
    if e.get('source_parent') != s.parent or e.get('completed_minute') is None:return 'parent_minute_provenance'
    minute=timestamp(e.get('completed_minute'))
    if minute is None or minute.second or minute.microsecond or ts<minute or ts-minute>timedelta(minutes=1):return 'completed_minute_provenance'
    if e.get('parent_votes') != [p for p in (s.parent,s.secondary) if p]:return 'parent_votes'
    if s.market_floor > -1e6:
        value=num(e.get('g11_market5'))
        if value is None:return 'market_evidence_unavailable'
        if value<s.market_floor:return 'market_regime'
    if s.min_symbol_vol>0 or s.max_symbol_vol<1e6:
        value=num(e.get('g11_symbol_vol'))
        if value is None:return 'volatility_evidence_unavailable'
        if not s.min_symbol_vol<=value<=s.max_symbol_vol:return 'volatility_regime'
    return None


def geometry(s,e,entry):
    if s.mode == 'FLASH':return primitives.geometry(s,e,entry)
    return entry*(1+s.fixed_target_pct/100),entry*(1-s.stop)


class FlashModule:
    PAPER_ONLY=True
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__=__name__+'.'+sid
    @property
    def CONFIG(self):return dict(metadata(self.STRATEGY_ID)['config'])
    def metadata(self):return metadata(self.STRATEGY_ID)
    def accepts_flash(self,e,maximum):return raw_accepts(SPECS[self.STRATEGY_ID],e,maximum)
    def refresh_event_for_entry(self,e,price):
        s=SPECS[self.STRATEGY_ID]
        r=dict(e,strategy_id=s.strategy_id,original_target_price=e.get('original_target_price',e.get('target_price')),
               original_flash_drop_pct=e.get('flash_drop_pct'),entry_price=price,paper_only=True,
               live_order_placement=False,research_generation=11,experimental_child=True,
               rule_version=RULE_VERSION,population_hash=POPULATION_HASH,config_hash=metadata(s.strategy_id)['config_hash'])
        geo=geometry(s,r,price)
        if geo:r.update(target_price=geo[0],stop_price=geo[1])
        r['remaining_upside_pct']=(r['target_price']/price-1)*100 if price>0 else -1.
        return r
    def validate_confirmed_entry(self,e,minimum):
        s=SPECS[self.STRATEGY_ID];t=timestamp(e.get('timestamp'))
        if t is None or t<timestamp(CREATED_UTC) or not time_admits(s,t):return False,'g11_time'
        return (True,None) if raw_accepts(s,e) else (False,'g11_raw')


MODULES={sid:FlashModule(sid) for sid in sorted(FLASH_IDS)}


class MinuteHub:
    """Seven owned raw-market evaluators; shared evidence, isolated accounts."""
    PAPER_ONLY=True
    name='G11HUB'
    def __init__(self):
        self.parents={}
        store=g6.FeatureStore()
        for parent in PARENTS:
            if parent in FLASH_PARENTS:continue
            if parent.startswith('G3'):e=g3.MinuteStrategy(parent)
            elif parent.startswith('G6'):e=g6.MinuteStrategy(parent,store=store)
            else:e=g7.Evaluator(g7._BY_ID[parent])
            self.parents[parent]=e
        self.history=defaultdict(lambda:deque(maxlen=16));self.coverage=defaultdict(int);self.last=None
    def on_snapshot(self,snapshot):
        t=timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond or self.last is not None and t<=self.last:return []
        if self.last is not None and (t-self.last!=timedelta(minutes=1) or t.astimezone(NY).date()!=self.last.astimezone(NY).date()):self.history.clear();self.coverage.clear()
        self.last=t
        for symbol in set(self.history)|set(snapshot.quotes):
            q=snapshot.quotes.get(symbol)
            if q is None or num(q.price,0)<=0:self.history[symbol].clear();self.coverage[symbol]=0
            else:self.history[symbol].append(float(q.price));self.coverage[symbol]=min(170,self.coverage[symbol]+1)
        events={p:{e.symbol:e for e in evaluator.on_snapshot(snapshot)} for p,evaluator in self.parents.items()}
        spy=list(self.history['SPY'])
        market5=(spy[-1]/spy[-6]-1)*100 if len(spy)>=6 else None
        ready={}
        for parent in self.parents:
            p=parent_spec(parent)
            if parent.startswith('G6'):
                n=p.lookback+3
                ready[parent]=self.coverage['SPY']>=n and any(self.coverage[x]>=n for x in p.universe if x!='SPY')
            elif parent.startswith('G3'):
                n=p.lookback+1
                ready[parent]=all(self.coverage[x]>=n for x in ('UNG','XLE'))
            else:
                n=self.parents[parent].module.PARAMS['lookback']+1
                ready[parent]=sum(self.coverage[x]>=n for x in g7.POOL)>=5
        ready_ids=[s.strategy_id for s in CATALOG if s.mode=='MINUTE' and ready[s.parent]
                   and (not s.secondary or ready[s.secondary])]
        result=[SignalEvent(t,'G11HUB','', 'G11_OBSERVATION',dict(ready_ids=ready_ids,completed_minute=t.isoformat()))]
        for s in CATALOG:
            if s.mode!='MINUTE':continue
            for symbol,e in events[s.parent].items():
                other=events.get(s.secondary,{}).get(symbol) if s.secondary else None
                if s.secondary and other is None:continue
                # G7 events are actionable one minute after the completed bar.
                actionable=max(e.timestamp, other.timestamp if other else e.timestamp)
                history=list(self.history[symbol])
                vol=statistics.pstdev([(b/a-1)*100 for a,b in zip(history[:-1],history[1:])]) if len(history)>=11 else None
                data=dict(e.data,source_parent=s.parent,parent_votes=[p for p in (s.parent,s.secondary) if p],
                          completed_minute=t.isoformat(),g11_market5=market5,g11_symbol_vol=vol,
                          paper_only=True,live_order_placement=False,research_generation=11,
                          experimental_child=True,rule_version=RULE_VERSION,population_hash=POPULATION_HASH,
                          config_hash=metadata(s.strategy_id)['config_hash'],research_metadata=metadata(s.strategy_id))
                result.append(SignalEvent(actionable,s.strategy_id,symbol,'SIGNAL',data))
        return result


class MinuteModule:
    PAPER_ONLY=True
    CONFIG={'live_order_placement':False}
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__=__name__+'.'+sid
    def metadata(self):return metadata(self.STRATEGY_ID)


ALL_MODULES={**MODULES, **{sid:MinuteModule(sid) for sid in MINUTE_IDS}}
