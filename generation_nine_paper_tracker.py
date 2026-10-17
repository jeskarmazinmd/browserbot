"""G9 paired paper groups. No broker client, credentials, or order capability.

Atomic paired admission/liquidation requires both full displayed quantities.
Short proceeds never finance entries. Gross collateral plus modeled costs is
reserved against cumulative $5k paper equity, with one group per ID. Missing liquidity defers the entire group;
latched exit reasons survive restart. This is a conservative paper model, not
proof that two exchange orders could execute atomically or that stock is borrowable.
"""
from dataclasses import asdict
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
from strategies import generation_nine as g
from strategies.output_switches import output_enabled

FILE_STEM='paper_generation_nine_sthedge2'

EXECUTION_VERSION = 'G9_WHOLE_SHARE_V2'
MAX_GROSS = 5000.
HEDGE_RELATIVE_TOLERANCE = .10
# Execution V2 supersedes Spec.gross_notional (frozen V1 provenance only).
LEGACY_TRACKER_HASH = 'fa572970dc462c51f23679e6c68b8716d42afb43002979db99b3b61c8cc318e9'


def size_pair(raw, quotes, now, spec, equity, used, sid):
    """Enumerate feasible integer pairs; gross collateral is a paper stress model.

    No broker margin, buying power or locate is verified by this calculation.
    Reserve gross plus both commissions and planned-hold borrow. Short proceeds
    are restricted and never counted as available equity.
    """
    legs=[]
    for leg in raw:
        q=quotes.get(leg['symbol'], {})
        if not g.valid_quote(q, now):return None, 'stale_or_invalid_quote'
        if (float(q['ask'])/float(q['bid'])-1)*10000>spec.max_spread_bps:return None, 'spread'
        side='ask' if leg['side']=='LONG' else 'bid'
        sign=1 if leg['side']=='LONG' else -1
        price=float(q[side])*(1+sign*spec.slippage_bps/10000)
        size=g.finite(q.get(side+'_size_raw',q.get(side+'_size')))
        if size is None:return None, 'missing_quote_size'
        key=(sid,leg['symbol'],side,str(q.get(side+'_time_ms',q.get('quote_time_ms'))))
        depth=max(0,math.floor(size*spec.participation)-used.get(key,0))
        legs.append(dict(symbol=leg['symbol'],side=leg['side'],weight=leg['weight'],
                         entry_price=price,quote=dict(q),book_key=list(key),depth=depth))
    prices=[x['entry_price'] for x in legs]
    cap=min(MAX_GROSS,max(0.,equity))
    if sum(prices)>MAX_GROSS:return None, 'insufficient_whole_share_allocation'
    if sum(prices)>cap:return None, 'insufficient_collateral_or_buying_power'
    target=raw[1]['weight']/raw[0]['weight']
    best=None;ratio_ok=False;collateral_ok=False
    # Enumerate SPY shares (the required coarse-priced hedge leg), and the
    # integer interval of first-leg shares allowed by the hedge tolerance.
    for n1 in range(1,math.floor(cap/prices[1])+1):
        lo=max(1,math.ceil(n1*prices[1]/(target*(1+HEDGE_RELATIVE_TOLERANCE)*prices[0])-1e-12))
        hi=min(math.floor((cap-n1*prices[1])/prices[0]),
               math.floor(n1*prices[1]/(target*(1-HEDGE_RELATIVE_TOLERANCE)*prices[0])+1e-12))
        for n0 in range(lo,hi+1):
            ratio_ok=True
            counts=[n0,n1];gross=sum(n*p for n,p in zip(counts,prices))
            candidate=[dict(x,shares=n) for x,n in zip(legs,counts)]
            costs=2*fee(candidate)+sum(x['shares']*x['entry_price'] for x in candidate if x['side']=='SHORT')*spec.borrow_bps_annual/10000*spec.max_hold_minutes/(365*24*60)
            if gross+costs>equity:continue
            collateral_ok=True
            if any(x['shares']>x['depth'] for x in candidate):continue
            error=abs((n1*prices[1]/(n0*prices[0]))/target-1)
            score=(gross,-error)
            if best is None or score>best[0]:best=(score,candidate,costs,error)
    if best is None:
        return None, ('hedge_ratio_mismatch' if not ratio_ok else
                      'insufficient_collateral_or_buying_power' if not collateral_ok else 'insufficient_displayed_liquidity')
    _,candidate,costs,error=best
    for x in candidate:x.pop('depth')
    return dict(legs=candidate,collateral_reserved=best[0][0]+costs,
                hedge_relative_error=error),None


def atomic(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as handle:
        handle.write(json.dumps(value,sort_keys=True)+'\n');handle.flush();os.fsync(handle.fileno())
    tmp.replace(path)


def source_hashes():
    root=Path(__file__).resolve().parent
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [root/'strategies/generation_nine.py',Path(__file__).resolve()]}


def fee(legs):
    return sum(max(.01,.005*x['shares']) for x in legs)


def borrow(row,now,spec):
    years=max(0.,(g.utc(now)-g.utc(row['opened_at'])).total_seconds())/(365*86400)
    return sum(x['shares']*x['entry_price'] for x in row['legs'] if x['side']=='SHORT')*spec.borrow_bps_annual/10000*years


def mark_group(row,quotes,now,spec,require_size=False,used=None):
    marks=[];pnl=0.
    for leg in row['legs']:
        q=quotes.get(leg['symbol'],{})
        if not g.valid_quote(q,g.utc(now)):return None
        side='bid' if leg['side']=='LONG' else 'ask'
        size=g.finite(q.get(side+'_size_raw',q.get(side+'_size')))
        identity=q.get(side+'_time_ms',q.get('quote_time_ms'))
        key=(row['strategy_id'],leg['symbol'],side,str(identity))
        if require_size and (size is None or math.floor(size*spec.participation)-(used or {}).get(key,0)<leg['shares']):return None
        sign=1 if leg['side']=='LONG' else -1
        price=float(q[side])*(1-sign*spec.slippage_bps/10000)
        pnl+=sign*(price-leg['entry_price'])*leg['shares']
        marks.append(dict(symbol=leg['symbol'],side=leg['side'],shares=leg['shares'],exit_price=price,
                          quote=dict(q),book_key=list(key)))
    net=pnl-row['entry_fee']-fee(row['legs'])-borrow(row,now,spec)
    return dict(pnl=net,gross_pnl=pnl,exit_fee=fee(row['legs']),borrow_fee=borrow(row,now,spec),exit_legs=marks,
                return_pct_on_gross_notional=net/row['gross_notional_used']*100)


class GenerationNineTracker:
    def __init__(self,root='/data',now_provider=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.clock=now_provider or (lambda:datetime.now(timezone.utc))
        self.lock=(self.root/(FILE_STEM+'.lock')).open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise RuntimeError('G9 writer already running')
        try:self._initialize()
        except BaseException:
            self.lock.close();raise

    def _initialize(self):
        self.ledger=self.root/(FILE_STEM+'_outcomes.jsonl')
        self.birth_path=self.root/(FILE_STEM+'_births.json')
        self.manifest_path=self.root/(FILE_STEM+'_manifest.json')
        expected=dict(rule_version=g.RULE_VERSION,population_hash=g.POPULATION_HASH,population=400,
                      sources=source_hashes(),specs=[asdict(s) for s in g.CATALOG])
        if self.manifest_path.exists():
            recorded=json.loads(self.manifest_path.read_text())
            legacy=dict(expected,sources=dict(expected['sources'], **{'generation_nine_paper_tracker.py':LEGACY_TRACKER_HASH}))
            if recorded not in (expected,legacy):raise ValueError('G9 frozen rules changed; new IDs required')
            if not self.birth_path.exists():raise ValueError('Missing G9 births; refuse reset')
        else:
            if self.ledger.exists() or self.birth_path.exists():raise ValueError('G9 orphan provenance; refuse reset')
            atomic(self.manifest_path,expected)
            atomic(self.birth_path,{sid:g.utc(self.clock()).isoformat() for sid in sorted(g.IDS)})
        self.execution_path=self.root/(FILE_STEM+'_execution_v2.json')
        policy=dict(version=EXECUTION_VERSION,max_gross=MAX_GROSS,hedge_tolerance=HEDGE_RELATIVE_TOLERANCE,
                    sources=source_hashes(),population_hash=g.POPULATION_HASH)
        if self.execution_path.exists():
            execution=json.loads(self.execution_path.read_text())
            if execution['policy']!=policy:raise ValueError('G9 execution policy changed')
        else:
            execution=dict(policy=policy,activated_at=g.utc(self.clock()).isoformat())
            atomic(self.execution_path,execution)
        self.execution_started_at=execution['activated_at']
        self.births=json.loads(self.birth_path.read_text())
        if set(self.births)!=g.IDS:raise ValueError('G9 birth population mismatch')
        for value in self.births.values():g.utc(value)
        self.active={};self.last={};self.realized={};self.used={};self.seen=set();self.completed=0;self.rejected={};self.rejection_reasons={};self.epoch_counts={};self.carry_days=set()
        if self.ledger.exists():
            with self.ledger.open() as handle:
                for line in handle:
                    row=json.loads(line);self._apply(row)
        self.status()

    def close(self):
        self.lock.close()

    def _apply(self,r):
        sid=r['strategy_id'];event=r['event']
        if sid not in g.IDS or g.utc(r['timestamp'])<g.utc(self.births[sid]):raise ValueError('Unknown/prebirth G9 event')
        epoch=r.get('execution_version','G9_LEGACY_V1')
        counts=self.epoch_counts.setdefault(epoch,dict(OPEN=0,CLOSE=0,REJECT=0,PENDING=0))
        counts[event]=counts.get(event,0)+1
        day=g.utc(r['timestamp']).astimezone(g.NY).date().isoformat()
        if event=='REJECT':
            self.rejected[sid]=self.rejected.get(sid,0)+1
            reason=r.get('reason','unknown');self.rejection_reasons[reason]=self.rejection_reasons.get(reason,0)+1
            reasons=counts.setdefault('rejection_reasons',{});reasons[reason]=reasons.get(reason,0)+1
            return
        gid=r['group_id']
        if event=='OPEN':
            gross=g.finite(r.get('gross_notional_used'))
            if (r.get('population_hash')!=g.POPULATION_HASH or gross is None or not 0<gross<=(MAX_GROSS if r.get('execution_version')==EXECUTION_VERSION else 1000.)+.000001
                    or len(r.get('legs',[]))!=2 or any(g.finite(x.get('shares')) is None or x['shares']<1
                        or int(x['shares'])!=x['shares'] or g.finite(x.get('entry_price')) is None
                        or x['entry_price']<=0 for x in r['legs'])):
                raise ValueError('Invalid G9 recorded entry')
            if sid in self.active or gid in self.seen:raise ValueError('Overlapping/duplicate G9 group')
            if r.get('execution_version')==EXECUTION_VERSION:
                if g.utc(r['timestamp'])<g.utc(self.execution_started_at):raise ValueError('Pre-execution G9 V2 entry')
                equity=5000.+sum(v for (strategy,_),v in self.realized.items() if strategy==sid)
                actual=sum(x['shares']*x['entry_price'] for x in r['legs'])
                target=r['legs'][1]['weight']/r['legs'][0]['weight']
                ratio=(r['legs'][1]['shares']*r['legs'][1]['entry_price'])/(r['legs'][0]['shares']*r['legs'][0]['entry_price'])
                if (abs(actual-gross)>1e-6 or abs(ratio/target-1)>HEDGE_RELATIVE_TOLERANCE+1e-10
                        or not gross+2*fee(r['legs'])<=r['collateral_reserved']<=equity+1e-6
                        or r.get('paper_only') is not True or r.get('broker_execution_enabled') is not False
                        or r.get('short_locate_verified') is not False):
                    raise ValueError('Invalid G9 V2 collateral/hedge/paper contract')
            self.seen.add(gid);self.active[sid]=r;self.last[sid]=g.utc(r['timestamp'])
            for leg in r['legs']:self._consume(leg['book_key'],leg['shares'])
        elif event=='PENDING':
            if sid not in self.active or self.active[sid]['group_id']!=gid:raise ValueError('Orphan G9 pending exit')
            self.active[sid]['pending_exit_reason']=r['reason']
        elif event=='CLOSE':
            if g.finite(r.get('pnl')) is None:raise ValueError('Invalid G9 recorded P&L')
            if sid not in self.active or self.active[sid]['group_id']!=gid:raise ValueError('Orphan G9 close')
            entry=self.active.pop(sid)
            entry_day=g.utc(entry['opened_at']).astimezone(g.NY).date().isoformat()
            # Carry outcomes remain in entry-day collateral; current-day reporting marks unknown.
            if entry_day!=day:self.carry_days.add((sid,day))
            key=(sid,entry_day);self.realized[key]=self.realized.get(key,0.)+r['pnl']
            for leg in r['exit_legs']:self._consume(leg['book_key'],leg['shares'])
            self.completed+=1
        else:raise ValueError('Unknown G9 event')

    def _consume(self,key,shares):
        key=tuple(key)
        # Only the latest quote identity for a given portfolio/symbol/side is useful.
        for old in list(self.used):
            if old[:3]==key[:3] and old!=key:self.used.pop(old)
        self.used[key]=self.used.get(key,0)+shares

    def append(self,row):
        row=dict(row,execution_version=EXECUTION_VERSION)
        with self.ledger.open('a') as handle:
            handle.write(json.dumps(row,sort_keys=True)+'\n');handle.flush();os.fsync(handle.fileno())
        self._apply(row)

    def reject(self,sid,now,reason):
        self.append(dict(event='REJECT',strategy_id=sid,timestamp=g.utc(now).isoformat(),reason=reason))
        return False

    def open(self,decision,quotes,now):
        now=g.utc(now);sid=decision['strategy_id'];s=g.SPECS[sid]
        if sid in self.active:return False
        if not output_enabled(sid) or os.environ.get('ENABLE_G9_PAPER','0')!='1':return False
        if (decision.get('paper_only') is not True or decision.get('live_order_placement') is not False
                or decision.get('population_hash')!=g.POPULATION_HASH):return self.reject(sid,now,'paper_contract')
        if g.utc(decision['timestamp'])!=now or now<g.utc(self.births[sid]) or now<g.utc(self.execution_started_at):return self.reject(sid,now,'signal_time')
        et=now.astimezone(g.NY)
        if et.weekday()>4 or not s.first_minute<=et.hour*60+et.minute<s.last_minute:return self.reject(sid,now,'entry_window')
        if sid in self.last and (now-self.last[sid]).total_seconds()<s.cooldown_minutes*60:return False
        raw=decision['legs']
        if len(raw)!=2 or raw[1]['symbol']!='SPY' or raw[0]['symbol']=='SPY' or {x['side'] for x in raw}!={'LONG','SHORT'}:return self.reject(sid,now,'invalid_pair')
        weights=[g.finite(x['weight']) for x in raw]
        if any(x is None or x<=0 for x in weights):return self.reject(sid,now,'invalid_weight')
        raw=[dict(leg,weight=w) for leg,w in zip(raw,weights)]
        day=et.date().isoformat()
        if (sid,day) in self.carry_days:return self.reject(sid,now,'carry_day_unverified')
        equity=5000.+sum(value for (strategy,_),value in self.realized.items() if strategy==sid)
        result,reason=size_pair(raw,quotes,now,s,equity,self.used,sid)
        if reason:return self.reject(sid,now,reason)
        legs=result['legs']
        gross=sum(x['entry_price']*x['shares'] for x in legs)
        self.append(dict(event='OPEN',strategy_id=sid,group_id=sid+'|'+now.isoformat(),timestamp=now.isoformat(),
                         opened_at=now.isoformat(),legs=legs,gross_notional_used=gross,entry_fee=fee(legs),
                         equity_before=equity,collateral_reserved=result['collateral_reserved'],
                         hedge_relative_error=result['hedge_relative_error'],
                         execution_feasibility='hypothetical; broker margin, buying power and locate unverified',
                         research=decision['research'],population_hash=g.POPULATION_HASH,paper_only=True,
                         broker_execution_enabled=False,broker_margin_verified=False,
                         broker_buying_power_verified=False,short_locate_verified=False))
        return True

    def update(self,quotes,now,population=None):
        now=g.utc(now);et=now.astimezone(g.NY)
        for sid,row in list(self.active.items()):
            s=g.SPECS[sid];reason=row.get('pending_exit_reason')
            mark=mark_group(row,quotes,now,s)
            if not reason:
                if (et.hour,et.minute)>=(15,55) or et.date()>g.utc(row['opened_at']).astimezone(g.NY).date():reason='EOD'
                elif (now-g.utc(row['opened_at'])).total_seconds()>=s.max_hold_minutes*60:reason='TIMEOUT'
                elif mark and mark['return_pct_on_gross_notional']>=s.target_pct:reason='TARGET'
                elif mark and mark['return_pct_on_gross_notional']<=-s.stop_pct:reason='STOP'
                elif s.exit_z>=0 and population:
                    f=population.feature(s,row['legs'][0]['symbol'])
                    # Cross-through counts as convergence, even if it overshoots zero.
                    if f and f['residual_z']*row['research']['residual_z']<=0:reason='CONVERGENCE'
                    elif f and abs(f['residual_z'])<=s.exit_z:reason='CONVERGENCE'
                if reason:self.append(dict(event='PENDING',strategy_id=sid,group_id=row['group_id'],timestamp=now.isoformat(),reason=reason))
            if not reason:continue
            fill=mark_group(row,quotes,now,s,require_size=True,used=self.used)
            if fill:
                self.append(dict(event='CLOSE',strategy_id=sid,group_id=row['group_id'],timestamp=now.isoformat(),
                                 opened_at=row['opened_at'],closed_at=now.isoformat(),exit_reason=reason,**fill,
                                 paper_only=True,broker_execution_enabled=False,broker_margin_verified=False,
                         broker_buying_power_verified=False,short_locate_verified=False,
                                 borrow_fee_model='assumed annual bps; actual borrow unavailable'))
        self.status()

    def status(self):
        atomic(self.root/(FILE_STEM+'_status.json'),dict(updated_at=g.utc(self.clock()).isoformat(),population=400,
            population_hash=g.POPULATION_HASH,known_births=len(self.births),active=len(self.active),completed=self.completed,
            seen_groups=len(self.seen),rejected=sum(self.rejected.values()),pending_exits=sum(bool(x.get('pending_exit_reason')) for x in self.active.values()),
            paper_only=True,broker_execution_enabled=False,quote_freshness_enforced=True,displayed_liquidity_enforced=True,
            starting_equity=5000.,max_gross_group_notional=MAX_GROSS,max_position_fraction=1.,
            execution_version=EXECUTION_VERSION,execution_started_at=self.execution_started_at,
            hedge_relative_tolerance=HEDGE_RELATIVE_TOLERANCE,rejection_reasons=self.rejection_reasons,
            counts_by_execution_version=self.epoch_counts,
            collateral_model='gross plus roundtrip commissions and planned-hold estimated borrow; no short proceeds',
            equity_model='5000 plus cumulative realized P&L per independent strategy',
            broker_margin_verified=False,broker_buying_power_verified=False,
            execution_feasibility='hypothetical research only; actual broker constraints unverified',
            one_group_per_strategy=True,historical_backfill_enabled=False,short_locate_verified=False,
            borrow_fees='estimated 300 annual bps; not verified',commission='0.005/share/side min 0.01 per leg',
            pricing='LONG ask->bid; SHORT bid->ask; full paired displayed quantity required',
            portfolio_combinable=False))
