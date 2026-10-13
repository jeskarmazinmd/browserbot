"""Thirty causal state/relationship mechanisms across four fixed economic routes.

Shared sampled-price features; independent evaluator episode state and portfolios.
No OHLC, volume, book imbalance, short borrow, or historical outcome fabrication.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import numpy as np
from engine.events import SignalEvent

NY = ZoneInfo('America/New_York')
SOURCE_COMMIT = 'fc22309f399dfb089e135022dc96b0c5abd2e3ee'
CREATED_UTC = '2026-10-13T20:34:29+00:00'
RULE_VERSION = 'generation_eight_frozen_v1'
_RAW = json.loads((Path(__file__).resolve().parents[1] / 'GENERATION_EIGHT_CATALOG.json').read_text())
POPULATION_HASH = hashlib.sha256(json.dumps(_RAW, sort_keys=True).encode()).hexdigest()
RULE_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
HISTORY = 96

@dataclass(frozen=True)
class Experiment:
    strategy_id: str
    mechanism_code: str
    route: str
    universe: tuple
    leaders: tuple
    votes: int = 1
    equity: float = 5000.
    notional: float = 1000.
    risk_fraction: float = .01
    max_position_fraction: float = .20
    portfolio_risk_fraction: float = .02
    one_position_per_symbol: bool = True
    max_entry_spread_pct: float = .10
    min_executable_upside_pct: float = .60
    min_target_spread_multiple: float = 8.
    max_quote_age_ms: float = 1000.
    displayed_participation: float = .10
    cooldown_seconds: int = 600
    stop_cooldown_seconds: int = 1800
    max_hold_seconds: int = 1800
    start_minute: int = 630
    end_minute: int = 930

CATALOG = tuple(Experiment(r['strategy_id'], r['strategy_id'][2:5], r['route'], tuple(r['universe']), tuple(r['leaders'])) for r in _RAW)
ALL_IDS = MINUTE_IDS = frozenset(s.strategy_id for s in CATALOG)
IDS = frozenset()  # Never a raw-flash subscription or broker route.
_BY_ID = {s.strategy_id: s for s in CATALOG}
_DESCRIPTIONS = {r['strategy_id']: r for r in _RAW}
ROUTES = {s.route: (s.universe, s.leaders) for s in CATALOG}
SYMBOLS = frozenset(x for s in CATALOG for x in s.universe + s.leaders)
assert len(CATALOG) == len(ALL_IDS) == 120

def timestamp(v):
    try:
        d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d if d.tzinfo else None
    except (ValueError, TypeError): return None

def spec_for(sid): return _BY_ID[sid]
def metadata(sid):
    s = spec_for(sid); d = _DESCRIPTIONS[sid]
    return dict(generation=8, strategy_id=sid, paper_only=True, config={'live_order_placement': False},
                source_commit=SOURCE_COMMIT, created_utc=CREATED_UTC, rule_version=RULE_VERSION,
                population_hash=POPULATION_HASH, rule_source_sha256=RULE_SOURCE_SHA256,
                parameters=asdict(s), hypothesis=d['admission'], novelty=d['novelty_comparison'],
                route_hypothesis=d['economic_test'], independent_discovery=False,
                prospective_start_policy='durable first activation; no historical credit or backfill')

def time_admits(s, value):
    t = timestamp(value)
    if t is None: return False
    et = t.astimezone(NY)
    return et.weekday() < 5 and s.start_minute <= et.hour * 60 + et.minute < s.end_minute

def _corr(a, b):
    a = a - a.mean(axis=0); b = b - b.mean(axis=0)
    den = np.sqrt((a*a).sum(axis=0)[:,None] * (b*b).sum(axis=0)[None,:])
    return np.divide(a.T @ b, den, out=np.zeros_like(den), where=den > 1e-12)

def _episodes(prices):
    """Completed sampled-close drawdowns; never an intraminute extreme claim."""
    peak = prices[0]; start = None; depth = area = 0.; complete = []
    for i, p in enumerate(prices[1:], 1):
        dd = 100 * (1 - p/peak)
        if start is None and dd > .05: start = i - 1; depth = area = 0.
        if start is not None:
            depth = max(depth, dd); area += max(0., dd)
            if p >= peak:
                complete.append((i-start, depth, area)); start = None
        if start is None: peak = max(peak, p)
    return complete[-3:]

def _route_features(p, universe, leaders):
    # Fixed training segment ends ten observations before the decision.
    n = len(universe); r = np.diff(np.log(p), axis=0) * 100
    train = r[-55:-10]; oldtrain = r[-70:-25]
    sd = train.std(axis=0); scale = np.maximum(sd, .003)
    r1 = r[-1]; r3 = r[-3:].sum(axis=0); r5 = r[-5:].sum(axis=0); r30 = r[-30:].sum(axis=0)
    r5old = r[-10:-5].sum(axis=0); r5older = r[-15:-10].sum(axis=0)
    ranks = [np.argsort(np.argsort(v[:n])) for v in (r5older, r5old, r5)]
    rank_churn = float(np.median(np.abs(ranks[2]-ranks[1])))
    lagcs = [_corr(train[:-lag], train[lag:]) for lag in (1,2,3)]
    graph = lagcs[0][:n,:n].copy(); np.fill_diagonal(graph, 0)
    oldgraph = _corr(oldtrain[:-1], oldtrain[1:])[:n,:n]; np.fill_diagonal(oldgraph, 0)
    hub = int(np.argmax((graph > .25).sum(axis=1))); oldhub = int(np.argmax((oldgraph > .25).sum(axis=1)))
    design = np.column_stack((np.ones(len(train)), train[:,n:]))
    beta = np.linalg.lstsq(design, train[:,:n], rcond=None)[0][1:]
    leader_corr = _corr(train[:,n:], train[:,n:]); np.fill_diagonal(leader_corr, 0)
    c_recent = _corr(r[-5:], r[-5:]); c_disrupted = _corr(r[-15:-5], r[-15:-5])
    leader_old = int(np.argmax(r5older[n:])); leader_new = int(np.argmax(r5[n:]))
    basket = r[:,:n].mean(axis=1); factor = r[:,n:].mean(axis=1)
    positive = (r5[:n] > 0).mean(); old_positive = (r5old[:n] > 0).mean()
    weighted = float(np.average(r5[:n], weights=np.maximum(r30[:n],0)+.01))
    old_weighted = float(np.average(r5old[:n], weights=np.maximum(r30[:n]-r5[:n],0)+.01))
    result = {}
    for j, symbol in enumerate(universe):
        own = r[:,j]; peer = np.delete(r[:,:n], j, axis=1).mean(axis=1)
        lead_scores = np.array([max(c[k,j] for c in lagcs) for k in range(n,p.shape[1])])
        l = n + int(np.argmax(lead_scores)); lag_strength = float(lead_scores.max())
        impulse = r[-8:-5,l].sum(); target_pre = r[-8:-5,j].sum()
        episodes = _episodes(p[:,j]); enough = len(episodes)==3
        durations = [e[0] for e in episodes]; depths = [e[1] for e in episodes]; areas = [e[2] for e in episodes]
        peer_episodes = [_episodes(p[:,k]) for k in range(n) if k!=j]
        peer_durations = [v[-1][0] for v in peer_episodes if v]
        records = np.flatnonzero(np.r_[False, p[1:,j] > np.maximum.accumulate(p[:-1,j])])
        intervals = np.diff(records)[-3:]
        negatives = [np.flatnonzero(r[-12:,k] < -.01) for k in (n,n+1,j)]
        order = [int(x[-1]) if len(x) else -1 for x in negatives]
        first = train[:,l] > 0; second = train[:,l] < 0
        def response(mask):
            x=train[mask,l]; y=train[mask,j]
            return float(np.dot(x,y)/np.dot(x,x)) if len(x)>=5 and np.dot(x,x)>1e-10 else None
        up, down = response(first), response(second)
        oldmask=oldtrain[:,l]<0;oldx=oldtrain[oldmask,l];oldy=oldtrain[oldmask,j]
        olddown=float(np.dot(oldx,oldy)/np.dot(oldx,oldx)) if len(oldx)>=5 and np.dot(oldx,oldx)>1e-10 else None
        positive_area=100*(p[-30:,j]/p[-30,j]-1)
        earlier_area=float(np.maximum(positive_area[:15],0).sum());retained_area=float(np.maximum(positive_area[15:],0).sum())
        normalized_peer_depths=[v[-1][1]/scale[k] for k,v in ((k,_episodes(p[:,k])) for k in range(n) if k!=j) if v]
        comparable_depth=bool(episodes and normalized_peer_depths and .5<=episodes[-1][1]/scale[j]/max(.001,float(np.median(normalized_peer_depths)))<=2.)
        stress1 = r[-30:-20,l].sum(); stress2=r[-20:-10,l].sum()
        target1=r[-30:-20,j].sum(); target2=r[-20:-10,j].sum()
        topold = int(np.argmax(r5old[:n])); margin = float(r5[j]-np.max(np.delete(r5[:n],j)))
        oldmargin = float(r5old[j]-np.max(np.delete(r5old[:n],j)))
        # Triads use prior and recent sampled returns; all are known at decision.
        tri = (j,n,n+1)
        old_coherence = float(np.mean([c_disrupted[a,b] for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0]))]))
        new_coherence = float(np.mean([c_recent[a,b] for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0]))]))
        leaveout = float(peer[-8:-5].sum())
        v = dict(price=float(p[-1,j]), ret1=float(r1[j]), ret3=float(r3[j]), ret5=float(r5[j]), ret30=float(r30[j]),
                 lagged_scale=float(scale[j]), lag_strength=lag_strength,
                 directed=bool(lag_strength>.25 and impulse>2*scale[l] and abs(target_pre)<abs(impulse)*.5 and r3[j]>0),
                 relay=bool(lagcs[0][n,n+1]>.25 and r[-9:-6,n].sum()>.04 and r[-6:-3,n+1].sum()>.04 and r3[j]>.04 and abs(target_pre)<abs(impulse)+.01),
                 quorum=bool(np.sum(r[-8:-5,n:].sum(axis=0)>2*scale[n:])>=2 and np.max(leader_corr)<.9 and lag_strength>.25),
                 braking=bool(impulse>.08 and 0<=r3[l]<impulse*.5 and r3[j]>r[-6:-3,j].sum() and target_pre<impulse*.5),
                 asymmetric=bool(up is not None and down is not None and olddown is not None and down<olddown and up>.25 and down<up*.5 and impulse>2*scale[l]),
                 reconcile=bool(r5old[n]*r5old[n+1]<0 and r5[n]>0 and r5[n+1]>0 and r5old[j]<max(r5old[n],r5old[n+1])),
                 breadth_transfer=bool(old_weighted>.04 and old_positive<.5 and positive>.5 and r5old[j]<=0),
                 sector_handoff=bool(r[-10:-5,n].sum()>.04 and r[-10:-5,n+1].sum()<=0 and r5[n+1]>.04 and r5old[j]<=0),
                 cancellation=bool(r5[n]>.08 and r5[n+1]<-.08 and abs(float(np.dot(beta[:,j],r5[n:])))<2*scale[j] and r30[j]>.05),
                 succession=bool(leader_old!=leader_new and r5[n+leader_new]>.04 and beta[leader_new,j]>.2 and positive>=old_positive),
                 migration=bool(ranks[0][j]<ranks[1][j]<ranks[2][j] and rank_churn<=2),
                 vacancy=bool(topold!=j and ranks[2][j]==n-1 and ranks[1][j]>=n//2 and ranks[2][topold]<n-2),
                 repair=bool(ranks[2][j]==n-1 and ranks[1][j]>=n-3 and margin>max(.01,oldmargin) and positive>=.5),
                 escape=bool(ranks[0][j]<=1 and ranks[2][j]>=n//2 and np.sum(r5[:n]>r5old[:n])>=n//2),
                 hysteresis=bool(ranks[0][j]>=n-2 and ranks[1][j]<n-2 and ranks[2][j]>=n-2 and positive>=.5),
                 cessation=bool(-1<order[0]<order[1]<order[2]<11 and r1[n]>=0 and r1[n+1]>=0),
                 leader_retest=bool(r[-15:-10,l].sum()>.08 and -.08<r[-10:-5,l].sum()<0 and r5[l]>.04 and r5old[j]<=0),
                 recovery_acceleration=bool(enough and durations[0]>durations[1]>durations[2] and depths[0]>=depths[1]>=depths[2] and peer[-5:].sum()>0),
                 immunity=bool(r[-12:-3,l].sum()<-.12 and own[-12:-3].sum()>-.02 and r1[l]>=0),
                 quiet_release=bool(r[-12:-7,l].sum()>.08 and np.max(np.abs(r[-7:-2,l]))<scale[l] and r[-7:-2,l].sum()>=0 and own[-7:-2].sum()<=.02),
                 retention=bool(episodes and np.sum(positive_area[15:]>0)>episodes[-1][0] and retained_area>earlier_area and r[-15:,j].sum()>.05),
                 first_passage=bool(episodes and peer_durations and comparable_depth and episodes[-1][0]<np.median(peer_durations)*.7 and r1[j]>0),
                 records=bool(len(intervals)==3 and intervals[0]>intervals[1]>intervals[2] and peer[-5:].sum()>0),
                 elasticity=bool(stress1<-.04 and stress2<-.04 and abs(target2/max(abs(stress2),.001))<abs(target1/max(abs(stress1),.001))*.7 and r5[l]>0),
                 underwater=bool(enough and areas[0]>areas[1]>areas[2] and peer[-5:].sum()>0),
                 hub_transfer=bool(hub!=oldhub and j!=hub and graph[hub,j]>.25 and r[-8:-5,hub].sum()>.04 and target_pre<r[-8:-5,hub].sum()),
                 periphery=bool(j==hub and np.sum((graph[:,j]>.25)&(r[-8:-5,:n].sum(axis=0)>.04))>=3 and target_pre<=.02),
                 reunion=bool(np.sum(oldgraph[j]>.25)>=2 and np.mean(c_disrupted[j,:n])<.1 and np.mean(c_recent[j,:n])>.35 and positive>.5),
                 diffusion=bool(leaveout>.04 and np.sum(r[-8:-5,:n].sum(axis=0)>.04)>=3 and target_pre<=.02 and float(_corr(np.delete(train[:-1,:n],j,axis=1).mean(axis=1)[:,None],train[1:,j][:,None])[0,0])>.25),
                 triad=bool(old_coherence<.1 and new_coherence>.45 and r5[n]>.04 and r5[n+1]>.04))
        result[symbol] = v
    return result

GATES = dict(zip(('T01','T02','T03','T04','T05','F01','F02','F03','F04','F05','R01','R02','R03','R04','R05','E01','E02','E03','E04','E05','X01','X02','X03','X04','X05','B01','B02','B03','B04','B05'),
                ('directed','relay','quorum','braking','asymmetric','reconcile','breadth_transfer','sector_handoff','cancellation','succession','migration','vacancy','repair','escape','hysteresis','cessation','leader_retest','recovery_acceleration','immunity','quiet_release','retention','first_passage','records','elasticity','underwater','hub_transfer','periphery','reunion','diffusion','triad')))

def admission_accepts(sid, evidence, symbol):
    s = spec_for(sid)
    if symbol not in s.universe or not isinstance(evidence,dict) or evidence.get(GATES[s.mechanism_code]) is not True: return False
    for k in ('price','ret1','ret3','ret5','lagged_scale'):
        if not isinstance(evidence.get(k),(int,float)) or not math.isfinite(evidence[k]):return False
    return evidence['price']>0 and evidence['ret1']>.003 and evidence['ret3']>0 and evidence['ret5']>0 and .003<=evidence['lagged_scale']<=2.

class FeatureStore:
    def __init__(self): self.history=defaultdict(lambda:deque(maxlen=HISTORY));self.last=None;self.rows={}
    def ingest(self,snapshot):
        t=timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond:return {}
        if self.last is not None and t<=self.last:return self.rows if t==self.last else {}
        if self.last is not None and (t-self.last!=timedelta(minutes=1) or t.astimezone(NY).date()!=self.last.astimezone(NY).date()):self.history.clear()
        self.last=t;self.rows={}
        for sym in SYMBOLS:
            q=snapshot.quotes.get(sym);p=getattr(q,'price',None)
            if not isinstance(p,(int,float)) or not math.isfinite(p) or p<=0:self.history[sym].clear()
            else:self.history[sym].append(p)
        return self.rows
    def features(self,snapshot,route):
        self.ingest(snapshot)
        if timestamp(snapshot.timestamp)!=self.last:return {}
        if route in self.rows:return self.rows[route]
        universe,leaders=ROUTES[route];symbols=universe+leaders
        if any(len(self.history[s])<HISTORY for s in symbols):return {}
        p=np.array([self.history[s] for s in symbols],dtype=float).T
        self.rows[route]=_route_features(p,universe,leaders)
        return self.rows[route]

_STORE=None
def shared_store():
    global _STORE
    if _STORE is None:_STORE=FeatureStore()
    return _STORE

def signal_row(s, symbol, evidence, completed_minute):
    p=evidence['price'];stop_pct=min(1.2,max(.4,evidence['lagged_scale']*math.sqrt(15)*2))
    target_pct=min(2.,max(.6,stop_pct*1.5))
    t=completed_minute+timedelta(minutes=1)
    return dict(strategy_id=s.strategy_id,symbol=symbol,timestamp=t.isoformat(),completed_minute=completed_minute.isoformat(),
                entry_price=p,target_price=p*(1+target_pct/100),stop_price=p*(1-stop_pct/100),
                g8_stop_pct=stop_pct,g8_target_pct=target_pct,admission_evidence=evidence,
                paper_only=True,live_order_placement=False,broker_execution_enabled=False,research_generation=8,
                rule_version=RULE_VERSION,population_hash=POPULATION_HASH,rule_source_sha256=RULE_SOURCE_SHA256,
                constituent_votes=[s.mechanism_code],research_metadata=metadata(s.strategy_id))

class Strategy:
    PAPER_ONLY=True
    def __init__(self,sid,store=None):self.name=sid;self.spec=spec_for(sid);self.store=store or shared_store();self.last=None;self.armed={};self.emitted={}
    def on_snapshot(self,snapshot):
        t=timestamp(snapshot.timestamp)
        if t is None or t.second or t.microsecond or (self.last is not None and t<=self.last):return []
        if self.last is not None and (t-self.last!=timedelta(minutes=1) or t.astimezone(NY).date()!=self.last.astimezone(NY).date()):self.armed.clear();self.emitted.clear()
        self.last=t;rows=self.store.features(snapshot,self.spec.route);result=[]
        if not time_admits(self.spec,t+timedelta(minutes=1)):return []
        for symbol in self.spec.universe:
            evidence=rows.get(symbol,{});ok=admission_accepts(self.name,evidence,symbol);prior=self.armed.get(symbol,False);self.armed[symbol]=ok
            if not ok or prior:continue
            last=self.emitted.get(symbol)
            if last and (t-last).total_seconds()<self.spec.cooldown_seconds:continue
            self.emitted[symbol]=t;row=signal_row(self.spec,symbol,evidence,t)
            result.append(SignalEvent(t+timedelta(minutes=1),self.name,symbol,'LONG',row))
        return result

for _sid in sorted(ALL_IDS):
    def _init(self,sid=_sid):Strategy.__init__(self,sid)
    globals()[_sid+'Strategy']=type(_sid+'Strategy',(Strategy,),{'__init__':_init,'__module__':__name__})
