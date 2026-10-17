"""Frozen long-only G3MPR150BA challengers. No broker capability.

All features are captured before admission. Missing required evidence fails
closed. The scanner supplies owned raw flash candidates, never parent trades.
"""
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
from strategies.generation_three import NY, time_admits
from strategies.generation_two import timestamp

PARENT = 'G3MPR150BA'
RULE_VERSION = 'G10_MPR150_V1'
CREATED_UTC = '2026-10-17T02:27:27+00:00'
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False


def num(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Spec:
    strategy_id: str = ''
    family: str = ''
    hypothesis: str = ''
    min_pre_return: float = 1.5
    min_pre_r2: float = .5
    min_flash_drop: float = 1.
    max_flash_drop: float = 12.
    rebound_fraction: float = .001
    pending_timeout: int = 600
    start_minute: int = 720
    end_minute: int = 840
    target_scale: float = 1.
    fixed_target_pct: float = 0.
    stop: float = .05
    trailing_pct: float = 0.
    trailing_arm_pct: float = .5
    breakeven_arm_pct: float = 0.
    max_hold_seconds: int = 10800
    checkpoint_seconds: int = 0
    checkpoint_gain_pct: float = 0.
    min_vol_pct: float = 0.
    max_vol_pct: float = 1e6
    min_shock_units: float = 0.
    max_shock_units: float = 1e6
    adaptive_stop_multiple: float = 0.
    market5_floor: float = -1e6
    market1_floor: float = -1e6
    min_volume_ratio: float = 0.
    min_dollar_volume: float = 0.
    min_price: float = 0.
    max_spread_pct: float = .20
    min_upside_pct: float = .20
    min_edge_spreads: float = 0.
    participation: float = .25
    max_quote_age_ms: int = 2000
    slippage_bps: float = 2.
    min_wait_seconds: int = 0
    max_recovery_fraction: float = 1.
    risk_fraction: float = .01
    max_position_fraction: float = .20
    portfolio_risk_fraction: float = .03
    cooldown_seconds: int = 0
    daily_loss_fraction: float = 1.
    one_position_per_symbol: bool = False


def _catalog():
    rows = []
    def family(name, changes):
        assert len(changes) == 20, (name, len(changes))
        for i, (hypothesis, values) in enumerate(changes, 1):
            rows.append(replace(Spec(), strategy_id=f'G10{name}{i:02d}', family=name,
                                hypothesis=hypothesis, **values))
    family('ENTRY', [('Parent entry under common G10 cost/accounting model', {})] +
        [(f'Pretrend at least {v}% selects stronger antecedent momentum', dict(min_pre_return=v)) for v in [1.,1.25,1.75,2.,2.25,2.5,3.]] +
        [(f'Pretrend R2 at least {v} excludes erratic ramps', dict(min_pre_r2=v)) for v in [.55,.6,.65,.7,.75,.8,.85]] +
        [(f'Minimum flash decline {v}% tests dislocation magnitude', dict(min_flash_drop=v)) for v in [1.25,1.5,1.75,2.,2.5]])
    family('TARGET', [(f'Recover {v:.0%} of executable remaining gap, reducing reversal exposure', dict(target_scale=v))
        for v in [.30,.35,.40,.45,.50,.55,.60,.65,.70,.75,.80,.85,.90,.95]] +
        [(f'Cap recovery target at {v}% above cost-adjusted ask', dict(fixed_target_pct=v)) for v in [.3,.4,.5,.6,.75,1.]])
    family('STOP', [(f'Tighten ask-anchored stop to {v:.1%}', dict(stop=v)) for v in [.005,.0075,.01,.0125,.015,.02,.025,.03,.035,.04]] +
        [(f'After 0.5% progress trail observed bid high by {v}%', dict(trailing_pct=v)) for v in [.2,.3,.4,.5,.75,1.]] +
        [(f'Arm cost-aware breakeven after {v}% progress', dict(breakeven_arm_pct=v)) for v in [.25,.5,.75,1.]])
    family('HOLD', [(f'Cap observed holding duration at {v} minutes', dict(max_hold_seconds=v*60)) for v in [3,5,8,10,15,20,30,45,60,90]] +
        [(f'At {m} minutes exit unless observed bid gain exceeds {gain}%',dict(checkpoint_seconds=m*60,checkpoint_gain_pct=gain))
         for m in [3,5,10,15,30] for gain in [0.,.25]])
    family('VOL', [(f'Preflash minute volatility in [{lo},{hi}]%',dict(min_vol_pct=lo,max_vol_pct=hi))
        for lo,hi in [(0.,.1),(0.,.2),(0.,.3),(.1,.3),(.1,.5),(.2,.5),(.2,1.),(.3,1.)]] +
        [(f'Flash shock in [{lo},{hi}] preflash standard deviations',dict(min_shock_units=lo,max_shock_units=hi))
         for lo,hi in [(3.,6.),(4.,8.),(5.,10.),(6.,12.),(4.,12.),(8.,20.)]] +
        [(f'Stop distance {v} times preflash volatility, bounded 0.5%-5%',dict(adaptive_stop_multiple=v)) for v in [2.,3.,4.,5.,6.,8.]])
    family('REGIME', [(f'Require contemporaneous market 5m return >= {v}%',dict(market5_floor=v)) for v in [-.5,-.25,-.1,0.,.1,.25]] +
        [(f'Adjacent predeclared ET entry window {a//60}:{a%60:02d}-{b//60}:{b%60:02d}',dict(start_minute=a,end_minute=b))
         for a,b in [(690,810),(750,870),(720,750),(750,780),(780,810),(810,840),(720,780),(780,840)]] +
        [(f'Require contemporaneous market 1m return >= {v}%',dict(market1_floor=v)) for v in [-.2,-.1,-.05,0.,.05,.1]])
    family('LIQ', [(f'Executable spread <= {v}% avoids costly recovery',dict(max_spread_pct=v)) for v in [.02,.03,.05,.075,.1,.15]] +
        [(f'Flash dollar volume >= ${v:g}, frozen at detection',dict(min_dollar_volume=v)) for v in [250000.,500000.,1000000.,5000000.]] +
        [(f'Executable price >= ${v:g}, price cohort without named-stock selection',dict(min_price=v)) for v in [2.,5.,10.,20.]] +
        [(f'Consume at most {v:.0%} of displayed book per quote identity',dict(participation=v)) for v in [.05,.1,.5]] +
        [(f'Require target gap >= {v} times spread',dict(min_edge_spreads=v)) for v in [4.,8.,12.]])
    family('CONFIRM', [(f'Wait for {v*100:g}% observed rebound from running trough',dict(rebound_fraction=v))
        for v in [.0005,.00075,.00125,.0015,.00175,.002,.0025,.003,.004,.005]] +
        [(f'Require at least {v}s of pending observation before rebound admission',dict(min_wait_seconds=v)) for v in [10,20,30,60,120]] +
        [(f'Reject if more than {v:.0%} of flash gap already recovered',dict(max_recovery_fraction=v)) for v in [.25,.35,.5,.65,.8]])
    family('RISK', [(f'Nominal stop risk {v:.2%} equity limits loss size',dict(risk_fraction=v)) for v in [.001,.002,.0025,.003,.004,.005,.006,.0075]] +
        [(f'Per-order cap {v:.0%} equity reduces concentration',dict(max_position_fraction=v)) for v in [.05,.1,.125,.15]] +
        [(f'Cooldown {v//60} minutes after any fill suppresses clustering',dict(cooldown_seconds=v)) for v in [300,600,1200,1800]] +
        [(f'Stop new entries after marked daily loss {v:.1%}; drain residuals',dict(daily_loss_fraction=v)) for v in [.005,.01,.015,.02]])
    combos = [
        ('Cheap spread and half-gap recovery',dict(max_spread_pct=.05,target_scale=.5)),
        ('High R2 and stronger rebound',dict(min_pre_r2=.75,rebound_fraction=.002)),
        ('Stronger pretrend and modest stop',dict(min_pre_return=2.,stop=.02)),
        ('One symbol at a time and ten-minute cooldown',dict(one_position_per_symbol=True,cooldown_seconds=600)),
        ('Fifteen-minute hold and partial recovery',dict(max_hold_seconds=900,target_scale=.65)),
        ('Tight spread and smaller risk',dict(max_spread_pct=.05,risk_fraction=.0025)),
        ('Avoid falling market and demand stronger trend',dict(market5_floor=0.,min_pre_return=2.)),
        ('Large shock with shallow observed recovery',dict(min_flash_drop=2.,max_recovery_fraction=.5)),
        ('Three-volatility stop and twenty-minute hold',dict(adaptive_stop_multiple=3.,max_hold_seconds=1200)),
        ('Five-minute progress check and quarter-percent trailing stop',dict(checkpoint_seconds=300,trailing_pct=.25)),
        ('Breakeven protection and 75% recovery target',dict(breakeven_arm_pct=.5,target_scale=.75)),
        ('High flash turnover and narrow spread',dict(min_dollar_volume=1000000.,max_spread_pct=.05)),
        ('No stacking and 1% aggregate nominal stop risk',dict(one_position_per_symbol=True,portfolio_risk_fraction=.01)),
        ('Two-times flash volume and smooth pretrend',dict(min_volume_ratio=2.,min_pre_r2=.7)),
        ('Late midday, tighter stop',dict(start_minute=780,stop=.02)),
        ('Early midday, half-gap recovery',dict(end_minute=780,target_scale=.5)),
        ('Stabilization and stronger rebound',dict(min_wait_seconds=30,rebound_fraction=.002)),
        ('Cost-adjusted target room and quarter book participation',dict(min_edge_spreads=8.,min_upside_pct=.75)),
        ('1% daily loss gate and ten-minute timeout',dict(daily_loss_fraction=.01,max_hold_seconds=600)),
        ('Narrow spread, bounded volatility, no stacking',dict(max_spread_pct=.05,max_vol_pct=.3,one_position_per_symbol=True)),
    ]
    family('COMBO', combos)
    return tuple(rows)


CATALOG = _catalog()
IDS = frozenset(s.strategy_id for s in CATALOG)
ALL_IDS = IDS
SPECS = {s.strategy_id: s for s in CATALOG}
assert len(CATALOG) == len(IDS) == 200


def semantic(s):
    return {k:v for k,v in asdict(s).items() if k not in {'strategy_id','family','hypothesis'}}


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,allow_nan=False).encode()).hexdigest()


assert len({digest(semantic(s)) for s in CATALOG}) == 200
POPULATION_HASH = digest([asdict(s) for s in CATALOG])
spec_for = SPECS.__getitem__


@lru_cache(maxsize=200)
def metadata(sid):
    s = SPECS[sid]
    return dict(strategy_id=sid,parent=PARENT,generation=10,family=s.family,
        description=s.hypothesis,hypothesis=s.hypothesis,parameters=asdict(s),
        config_hash=digest(asdict(s)),population_hash=POPULATION_HASH,
        rule_version=RULE_VERSION,paper_only=True,broker_execution_enabled=False,
        created_utc=CREATED_UTC,prospective_start_policy='durable first activation; no backfill',
        config=dict(flash_drop_pct=s.min_flash_drop,rebound_confirmation_pct=s.rebound_fraction,
            pending_rebound_timeout_seconds=s.pending_timeout,min_remaining_upside_pct=.20,
            stop_loss_fraction=s.stop,live_order_placement=False))


def raw_accepts(s,e,maximum=12.):
    drop=num(e.get('original_flash_drop_pct',e.get('flash_drop_pct')))
    pre=num(e.get('pre_return_pct'));r2=num(e.get('pre_r2'))
    return (drop is not None and pre is not None and r2 is not None and
        s.min_flash_drop<=drop<=min(maximum,s.max_flash_drop) and pre>=s.min_pre_return and s.min_pre_r2<=r2<=1.)


def admission(s,e,ask,bid,now):
    if not raw_accepts(s,e):return 'raw_predicate'
    ts=timestamp(e.get('timestamp'))
    if ts is None or not time_admits(s,ts) or not time_admits(s,now):return 'time_window'
    if ask<s.min_price:return 'price_cohort'
    vol=num(e.get('pre30_return_std_pct'))
    if s.min_vol_pct>0 or s.max_vol_pct<1e6 or s.adaptive_stop_multiple>0 or s.min_shock_units>0:
        if vol is None or vol<=0:return 'missing_volatility'
        feature_time=timestamp(e.get('flash_snapshot_time'))
        if feature_time is None or feature_time>ts or e.get('volume_data_status_flash')!='OK':return 'volatility_provenance'
        if not s.min_vol_pct<=vol<=s.max_vol_pct:return 'volatility_cohort'
        units=num(e.get('original_flash_drop_pct',e.get('flash_drop_pct')))/vol
        if not s.min_shock_units<=units<=s.max_shock_units:return 'shock_units'
    for field,floor in [('market_5m_return_pct',s.market5_floor),('market_1m_return_pct',s.market1_floor)]:
        if floor>-1e6:
            value=num(e.get(field))
            if value is None or e.get('market_confirmation_symbol') not in {'SPY','QQQ'}:return 'missing_market_evidence'
            feature_time=timestamp(e.get('market_feature_time'))
            if feature_time is None or feature_time>ts or (ts-feature_time).total_seconds()>120:return 'market_provenance'
            if value<floor:return 'market_regime'
    for field,floor in [('flash_volume_ratio',s.min_volume_ratio),('flash_dollar_volume_3m',s.min_dollar_volume)]:
        if floor>0:
            value=num(e.get(field))
            if value is None or e.get('volume_data_status_flash')!='OK':return 'missing_volume_evidence'
            feature_time=timestamp(e.get('flash_snapshot_time'))
            if feature_time is None or feature_time>ts:return 'volume_provenance'
            if value<floor:return 'volume_filter'
    if s.min_wait_seconds:
        wait=num(e.get('confirmation_wait_seconds'))
        if wait is None or wait<s.min_wait_seconds:return 'insufficient_persistence'
    if s.max_recovery_fraction<1:
        low=num(e.get('running_low_price'));original=num(e.get('flash_start_price'))
        if low is None or original is None or not 0<low<original:return 'missing_trough_evidence'
        if (ask-low)/(original-low)>s.max_recovery_fraction:return 'recovery_overshoot'
    return None


def geometry(s,e,entry):
    original=num(e.get('original_target_price'))
    if original is None or original<=entry:return None
    stop=s.stop
    if s.adaptive_stop_multiple:
        vol=num(e.get('pre30_return_std_pct'))
        if vol is None or vol<=0:return None
        stop=max(.005,min(.05,s.adaptive_stop_multiple*vol/100))
    target=entry+(original-entry)*s.target_scale
    if s.fixed_target_pct:target=min(target,entry*(1+s.fixed_target_pct/100))
    return target,entry*(1-stop)


def executable_votes(sid,e,ask,bid):
    return (PARENT,) if raw_accepts(SPECS[sid],e) else ()


class FlashModule:
    PAPER_ONLY=True
    def __init__(self,sid):self.STRATEGY_ID=sid;self.__name__='strategies.generation_ten.'+sid
    @property
    def CONFIG(self):return dict(metadata(self.STRATEGY_ID)['config'])
    def metadata(self):return metadata(self.STRATEGY_ID)
    def accepts_flash(self,e,maximum):return raw_accepts(SPECS[self.STRATEGY_ID],e,maximum)
    def refresh_event_for_entry(self,e,price):
        s=SPECS[self.STRATEGY_ID];r=dict(e)
        original=num(e.get('target_price'))
        r.update(strategy_id=s.strategy_id,original_target_price=original,
            original_flash_drop_pct=e.get('flash_drop_pct'),entry_price=price,
            stop_price=price*(1-s.stop),target_price=original,paper_only=True,
            live_order_placement=False,research_generation=10,experimental_child=True,
            forward_start_utc=CREATED_UTC,rule_version=RULE_VERSION,population_hash=POPULATION_HASH,
            config_hash=metadata(s.strategy_id)['config_hash'])
        geo=geometry(s,r,price)
        if geo:r.update(target_price=geo[0],stop_price=geo[1])
        r['remaining_upside_pct']=(r['target_price']/price-1)*100 if price>0 else -1.
        return r
    def validate_confirmed_entry(self,e,minimum):
        ts=timestamp(e.get('timestamp'));s=SPECS[self.STRATEGY_ID]
        if ts is None or ts<timestamp(CREATED_UTC) or not time_admits(s,ts):return False,'g10_time'
        if not raw_accepts(s,e):return False,'g10_raw'
        entry=num(e.get('entry_price'));target=num(e.get('target_price'))
        if entry is None or target is None or entry<=0 or (target/entry-1)*100<.20:return False,'g10_geometry'
        return True,None


MODULES={sid:FlashModule(sid) for sid in sorted(IDS)}
