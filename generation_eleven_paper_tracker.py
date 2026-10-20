"""Durable isolated G11 long-only accounts, using shared executable BA primitives.

Cumulative cash (no midnight reset), whole shares, partial fills, per-side book
consumption, conservative adverse slippage and modeled commissions. No broker
imports. A pending stop/time exit survives missing liquidity and process restart.
"""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import base64
import zlib
import hashlib
import json
import math
import os
from pathlib import Path
from executable_paper_engine import classify_limit_order, executable_mark, _utc
from strategies import generation_eleven as g
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned

FILE_STEM='paper_generation_eleven_bidask_independent'
IDS=g.IDS
EXECUTION_VERSION='G11_LONG_CASH_V1'


def decode_snapshot(row):
    if row.get('event')=='SNAPSHOT' and 'account_frame_zlib_base64' in row:
        data=json.loads(zlib.decompress(base64.b64decode(row['account_frame_zlib_base64'],validate=True)))
        return dict(row,**data)
    return row


def fee(qty, sell=False):
    # Explicit research assumptions, not a claim about Schwab's actual tariff.
    return max(.01,.005*qty)+(.0002*qty if sell else 0.)


def atomic(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        f.write(json.dumps(value,sort_keys=True,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    tmp.replace(path)


def source_hashes():
    root=Path(__file__).resolve().parent
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
        ['strategies/generation_eleven.py','generation_eleven_paper_tracker.py','executable_paper_engine.py',
         'strategies/generation_ten.py','strategies/generation_three.py','strategies/generation_six.py',
         'strategies/generation_seven.py','strategies/strategy_cmdrot1.py',
         'strategies/generation_eleven_retirement.py','strategies/output_switches.py']}


def valid_book(q, now, s, both=True):
    for action in (('BUY','SELL') if both else ('SELL',)):
        m=executable_mark(q,action=action,now=now,max_quote_age_ms=s.max_quote_age_ms)
        if m['state']!='EXECUTABLE':return m['reason']
        if m.get('quote_age_ms',-1)<0:return 'future_quote'
        side='ask' if action=='BUY' else 'bid'
        if g.num((q or {}).get(side+'_time_ms',(q or {}).get('quote_time_ms'))) is None:return 'missing_side_timestamp'
    return None


def mark_position(row,q,now,s):
    if valid_book(q,now,s,both=False):return None
    price=float(q['bid'])*(1-s.slippage_bps/10000)
    qty=row['remaining_qty']
    return dict(liquidation_value=qty*price-fee(qty,True),bid=price,
                # High/low are observed polls, not unobserved intrapoll extremes.
                unrealized_pnl=qty*(price-row['entry_price'])-fee(qty,True))


class GenerationElevenTracker:
    def __init__(self,root='/data',now_provider=None,**unused):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.clock=now_provider or (lambda:datetime.now(timezone.utc))
        self.lock=(self.root/(FILE_STEM+'.lock')).open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise RuntimeError('G11 writer already running')
        try:
            from strategies.generation_eleven_retirement import require_activation
            require_activation(self.root)
            self._initialize()
            (self.root/(FILE_STEM+'_error.json')).unlink(missing_ok=True)
        except BaseException:
            self.close();raise

    def _initialize(self):
        self.ledger_path=self.root/(FILE_STEM+'_outcomes.jsonl')
        self.birth_path=self.root/(FILE_STEM+'_births.json')
        self.manifest_path=self.root/(FILE_STEM+'_manifest.json')
        expected=dict(population_hash=g.POPULATION_HASH,rule_version=g.RULE_VERSION,
            execution_version=EXECUTION_VERSION,sources=source_hashes(),population=722,
            specs=[dict(**asdict(s),config_hash=g.metadata(s.strategy_id)['config_hash'],parent_report=g.metadata(s.strategy_id)['parent'],
                        paper_only=True,broker_execution_enabled=False) for s in g.CATALOG])
        if self.manifest_path.exists():
            manifest=json.loads(self.manifest_path.read_text())
            if {k:v for k,v in manifest.items() if k!='births'}!=expected:raise ValueError('G11 frozen source/config changed; use new IDs')
            if not self.birth_path.exists():raise ValueError('G11 births missing; refuse reset')
            self.births=json.loads(self.birth_path.read_text())
            if self.births!=manifest['births']:raise ValueError('G11 birth evidence mismatch')
        else:
            if self.ledger_path.exists() or self.birth_path.exists():raise ValueError('G11 orphan provenance; refuse reset')
            birth=max(_utc(self.clock()),_utc(g.CREATED_UTC)).isoformat()
            self.births={sid:birth for sid in sorted(IDS)}
            atomic(self.manifest_path,dict(expected,births=self.births))
            atomic(self.birth_path,self.births)
        if set(self.births)!=IDS:raise ValueError('G11 population mismatch')
        for t in self.births.values():_utc(t)
        self.cash={sid:5000. for sid in IDS};self.active={};self.seen=set();self.used={}
        self.last={};self.completed=Counter();self.rejections=Counter();self.reasons=Counter()
        self.observed={};self.snapshots={};self.state={};self.seq=0;self.last_time=None;self.last_snapshot_time=None
        if self.ledger_path.exists():
            with self.ledger_path.open() as f:
                for line in f:self._apply(json.loads(line))
        self.status()

    def close(self):self.lock.close()

    def _apply(self,r):
        r=decode_snapshot(r)
        if r.get('sequence')!=self.seq+1:raise ValueError('G11 ledger sequence mismatch')
        t=_utc(r['timestamp']);sid=r.get('strategy_id');kind=r['event']
        if self.last_time is not None and t<self.last_time:raise ValueError('G11 nonchronological ledger')
        if sid is not None and (sid not in IDS or t<_utc(self.births[sid])):raise ValueError('G11 unknown/prebirth event')
        if r.get('execution_version')!=EXECUTION_VERSION or r.get('paper_only') is not True or r.get('broker_execution_enabled') is not False:raise ValueError('G11 ledger paper contract')
        if kind=='OPEN':
            key=r['setup_id'];qty=r['remaining_qty'];price=r['entry_price']
            if key in self.seen or type(qty) is not int or qty<=0 or g.num(price,0)<=0:raise ValueError('G11 duplicate/invalid entry')
            if (g.num(r.get('entry_fee'))!=fee(qty) or r.get('filled_qty')!=qty or
                g.num(r.get('target_price'),0)<=price or not 0<g.num(r.get('stop_price'),0)<price or
                r.get('research',{}).get('config_hash')!=g.metadata(sid)['config_hash']):raise ValueError('G11 invalid entry accounting')
            debit=qty*price+r['entry_fee']
            if debit>self.cash[sid]+1e-6:raise ValueError('G11 negative buying power')
            self.cash[sid]-=debit;self.active[key]=dict(r);self.seen.add(key);self.last[sid]=t
            self._consume(r['book'])
        elif kind=='FILL':
            key=r['setup_id'];a=self.active.get(key)
            if not a or a['strategy_id']!=sid or not 0<r['qty']<=a['remaining_qty']:raise ValueError('G11 orphan/oversized exit')
            if type(r['qty']) is not int or g.num(r.get('price'),0)<=0 or g.num(r.get('fee'))!=fee(r['qty'],True):raise ValueError('G11 invalid exit accounting')
            if abs(r['pnl']-(r['qty']*(r['price']-a['entry_price'])-r['fee']))>1e-7 or bool(r['final'])!=(r['qty']==a['remaining_qty']):raise ValueError('G11 invalid exit P&L')
            proceeds=r['qty']*r['price']-r['fee']
            if abs(proceeds-r['proceeds'])>1e-7:raise ValueError('G11 exit arithmetic')
            self.cash[sid]+=proceeds;a['remaining_qty']-=r['qty'];a['realized_net']+=r['pnl']
            self._consume(r['book'])
            if not a['remaining_qty']:
                self.completed[sid]+=1;self.active.pop(key)
        elif kind=='STATE':
            a=self.active.get(r['setup_id'])
            if a is None:raise ValueError('G11 orphan state')
            a.update(r['changes'])
        elif kind=='REJECT':
            self.seen.add(r['setup_id']);self.rejections[sid]+=1;self.reasons[r['reason']]+=1
        elif kind=='OBSERVE':self.observed.update(r['observations'])
        elif kind=='SNAPSHOT':
            self.snapshots=r['accounts'];self.state=r['drawdown_state'];self.last_snapshot_time=t
        else:raise ValueError('G11 unknown event')
        self.seq=r['sequence'];self.last_time=t

    def _consume(self,book):self.used[book['key']]={'stamp':book['stamp'],'used':book['used']}

    def append(self,kind,now,**data):
        if kind=='SNAPSHOT':
            # Lossless complete frames, not lossy compaction. Keep all account
            # observations while bounding disk growth across 722 strategies.
            payload=json.dumps(data,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
            data=dict(account_frame_zlib_base64=base64.b64encode(zlib.compress(payload,1)).decode())
        row=dict(event=kind,timestamp=_utc(now).isoformat(),sequence=self.seq+1,
            execution_version=EXECUTION_VERSION,paper_only=True,broker_execution_enabled=False,**data)
        # Single-writer sequenced log; corrupt or incomplete records fail closed on recovery.
        if self.last_time and _utc(now)<self.last_time:raise ValueError('G11 clock moved backwards')
        with self.ledger_path.open('a') as f:
            f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
        self._apply(row)
        return row

    def reject(self,sid,setup,now,reason,signal=None):
        self.append('REJECT',now,strategy_id=sid,setup_id=setup,reason=reason,
            signal={k:v for k,v in (signal or {}).items() if k not in {'research_metadata','research','admission_evidence'}})
        return False

    def book(self,sid,symbol,q,action,now):
        s=g.SPECS[sid];side='ask' if action=='BUY' else 'bid';key=f'{sid}|{symbol}|{side}'
        adjusted=dict(q);stamp=g.num(q.get(side+'_time_ms',q.get('quote_time_ms')))
        saved=self.used.get(key);used=0
        if saved:
            if stamp is None or stamp<saved['stamp']:return None,None,'older_book'
            if stamp==saved['stamp']:used=saved['used']
        size=g.num(q.get(side+'_size_raw',q.get(side+'_size')))
        if size is None or stamp is None:return None,None,'missing_displayed_liquidity'
        adjusted[side+'_size_raw']=max(0,math.floor(size*s.participation)-used)
        return adjusted,dict(key=key,stamp=stamp,used=used),None

    def register_signal(self,signal,quote,now,portfolio_quotes=None):
        now=_utc(now);sid=signal.get('strategy_id')
        if sid not in IDS or os.environ.get('ENABLE_G11_PAPER','0')!='1':return False
        if not output_enabled(sid) or not output_enabled(sid+'BA') or output_is_pruned(sid):return False
        s=g.SPECS[sid];ts=g.timestamp(signal.get('timestamp'));symbol=str(signal.get('symbol') or '').upper()
        # A source setup ID never lets two challengers share dedup state.
        identity=str(signal.get('signal_window_end') or signal.get('pending_created_at') or (ts.isoformat() if ts else 'missing'))
        key=f'{sid}|{symbol}|{identity}'
        if key in self.seen:return False
        if now<_utc(self.births[sid]):return False
        if ts is None or ts<_utc(self.births[sid]) or ts>now or (now-ts).total_seconds()>120:return self.reject(sid,key,now,'signal_time',signal)
        if (signal.get('paper_only') is not True or signal.get('live_order_placement') is not False or
            signal.get('rule_version')!=g.RULE_VERSION or signal.get('population_hash')!=g.POPULATION_HASH or
            signal.get('config_hash')!=g.metadata(sid)['config_hash']):return self.reject(sid,key,now,'paper_contract',signal)
        if s.mode == 'MINUTE':
            minute=g.timestamp(signal.get('completed_minute'))
            if minute is None or minute<_utc(self.births[sid]):return self.reject(sid,key,now,'prebirth_minute',signal)
        if s.mode == 'FLASH':
            initial=g.timestamp(signal.get('pending_created_at'))
            if initial is None or initial<_utc(self.births[sid]) or initial>ts:return self.reject(sid,key,now,'prebirth_or_missing_pending',signal)
            wait=(ts-initial).total_seconds()
            if wait>=s.pending_timeout:return self.reject(sid,key,now,'pending_timeout',signal)
        if not symbol:return self.reject(sid,key,now,'missing_symbol',signal)
        low=None
        if s.mode == 'FLASH':
            rebound=g.num(signal.get('actual_rebound_pct'))
            reference=g.num(signal.get('entry_price'));low=g.num(signal.get('running_low_price'))
            if rebound is None or rebound+1e-10<s.rebound_fraction*100 or reference is None or low is None or low<=0 or reference<low*(1+s.rebound_fraction)-1e-9:
                return self.reject(sid,key,now,'rebound_evidence',signal)
        reason=valid_book(quote,now,s)
        if reason:return self.reject(sid,key,now,reason,signal)
        q=dict(quote);ask=float(q['ask']);bid=float(q['bid'])
        if s.mode == 'FLASH' and ask<low*(1+s.rebound_fraction)-1e-9:return self.reject(sid,key,now,'executable_rebound_lost',signal)
        reason=g.admission(s,signal,ask,bid,now)
        if reason:return self.reject(sid,key,now,reason,signal)
        if (ask/bid-1)*100>s.max_spread_pct:return self.reject(sid,key,now,'spread',signal)
        entry=ask*(1+s.slippage_bps/10000);geo=g.geometry(s,signal,entry)
        if geo is None:return self.reject(sid,key,now,'target_geometry',signal)
        target,stop=geo
        if (target/entry-1)*100<s.min_upside_pct or target-entry<s.min_edge_spreads*(ask-bid):return self.reject(sid,key,now,'net_target_room',signal)
        if stop>=bid*(1-s.slippage_bps/10000):return self.reject(sid,key,now,'stop_inside_spread',signal)
        if sid in self.last and (now-self.last[sid]).total_seconds()<s.cooldown_seconds:return self.reject(sid,key,now,'cooldown',signal)
        positions=[r for r in self.active.values() if r['strategy_id']==sid]
        if s.one_position_per_symbol and any(r['symbol']==symbol for r in positions):return self.reject(sid,key,now,'symbol_already_open',signal)
        if any(_utc(r['timestamp']).astimezone(g.NY).date()!=now.astimezone(g.NY).date() for r in positions):return self.reject(sid,key,now,'overnight_residual',signal)
        # Use the lower of marked liquidation equity and cost equity. Stale
        # residual marks cannot support another position or inflate buying power.
        cash=self.cash[sid];equity=cash+sum(r['remaining_qty']*r['entry_price'] for r in positions)
        marks=[mark_position(r,q if r['symbol']==symbol else (portfolio_quotes or {}).get(r['symbol']),now,s) for r in positions]
        if any(m is None for m in marks):return self.reject(sid,key,now,'portfolio_mark_unavailable',signal)
        equity=min(equity,cash+sum(m['liquidation_value'] for m in marks))
        if s.daily_loss_fraction<1:
            state=self.state.get(sid,{})
            if state.get('day')!=now.astimezone(g.NY).date().isoformat() or state.get('unknown') or state.get('day_start_equity') is None:return self.reject(sid,key,now,'daily_risk_mark_missing',signal)
            marked=cash+sum(m['liquidation_value'] for m in marks)
            if marked is None or marked<=state['day_start_equity']*(1-s.daily_loss_fraction):return self.reject(sid,key,now,'daily_loss_limit',signal)
        risk=sum(r['remaining_qty']*max(0,r['entry_price']-r['stop_price']) for r in positions)
        symbol_cost=sum(r['remaining_qty']*r['entry_price'] for r in positions if r['symbol']==symbol)
        budget=max(0,min(1000.,equity*s.max_position_fraction-symbol_cost,cash-.01))
        per_risk=entry-stop+.01
        qty=max(0,min(math.floor(budget/entry),math.floor(equity*s.risk_fraction/per_risk),
                    math.floor(max(0,equity*s.portfolio_risk_fraction-risk)/per_risk)))
        while qty>0 and qty*entry+fee(qty)>cash:qty-=1
        if qty<1:return self.reject(sid,key,now,'insufficient_cash_or_risk_budget',signal)
        adjusted,book,reason=self.book(sid,symbol,q,'BUY',now)
        if reason:return self.reject(sid,key,now,reason,signal)
        decision=classify_limit_order(adjusted,action='BUY',limit_price=ask,requested_qty=qty,now=now,max_quote_age_ms=s.max_quote_age_ms)
        if decision.outcome not in {'FULL','PARTIAL'}:return self.reject(sid,key,now,decision.reason,signal)
        filled=decision.filled_qty;book['used']+=filled
        if self.state.get(sid,{}).get('day') != now.astimezone(g.NY).date().isoformat():
            self.snapshot(portfolio_quotes or {symbol:q},now)
        self.append('OPEN',now,strategy_id=sid,setup_id=key,symbol=symbol,entry_price=entry,
            entry_fee=fee(filled),filled_qty=filled,remaining_qty=filled,target_price=target,stop_price=stop,
            initial_stop_price=stop,peak_bid=bid,realized_net=-fee(filled),pending_exit_reason=None,
            book=book,quote=q,decision=decision.as_dict(),signal=dict(signal),research=g.metadata(sid),
            cost_model='adverse slippage + $0.005/share/side min $0.01; sell $0.0002/share; assumed')
        return True

    def symbols(self,limit=400):
        # All held symbols must be requested; silently truncating strands positions.
        return {r['symbol'] for r in self.active.values()}

    def observe_scan(self,now,symbols_seen,ready_windows=None):
        now=_utc(now)
        if symbols_seen<=0:return
        ready_windows=symbols_seen if ready_windows is None else ready_windows
        day=now.astimezone(g.NY).date().isoformat();obs={}
        for s in g.CATALOG:
            sid=s.strategy_id
            if s.mode != 'FLASH' or now<_utc(self.births[sid]) or not g.time_admits(s,now):continue
            prior=self.observed.get(sid,{})
            if prior.get('last_minute')==now.replace(second=0,microsecond=0).isoformat():continue
            count=prior.get('scans',0) if prior.get('day')==day else 0
            obs[sid]=dict(day=day,scans=count+1,symbols_seen=symbols_seen,ready_windows=ready_windows,last_minute=now.replace(second=0,microsecond=0).isoformat())
        if obs:self.append('OBSERVE',now,observations=obs)

    def observe_minute(self,now,ready_ids=None,completed_minute=None):
        now=_utc(now)
        day=now.astimezone(g.NY).date().isoformat()
        ready=set(ready_ids or ())
        completed=_utc(completed_minute) if completed_minute is not None else now
        if completed>now or (now-completed).total_seconds()>120:return
        obs={s.strategy_id:dict(day=day,ready_windows=1,last_minute=completed.isoformat())
             for s in g.CATALOG if s.mode=='MINUTE' and s.strategy_id in ready
             and completed>=_utc(self.births[s.strategy_id]) and g.time_admits(s,completed)}
        if obs:self.append('OBSERVE',now,observations=obs)

    def update_quotes(self,quotes,now):
        now=_utc(now);closed=[];et=now.astimezone(g.NY)
        for key,r in list(self.active.items()):
            sid=r['strategy_id'];s=g.SPECS[sid];age=(now-_utc(r['timestamp'])).total_seconds()
            reason=r.get('pending_exit_reason');q=quotes.get(r['symbol']);mark=mark_position(r,q,now,s)
            stop=r['stop_price'];peak=r['peak_bid']
            if not reason:
                if et.date()>_utc(r['timestamp']).astimezone(g.NY).date() or et.hour*60+et.minute>=955:reason='EOD'
                elif age>=s.max_hold_seconds:reason='MAX_HOLD'
                if mark:
                    price=mark['bid'];peak=max(peak,price);gain=(price/r['entry_price']-1)*100
                    peak_gain=(peak/r['entry_price']-1)*100
                    if s.trailing_pct and peak_gain>=s.trailing_arm_pct:stop=max(stop,peak*(1-s.trailing_pct/100))
                    if s.breakeven_arm_pct and peak_gain>=s.breakeven_arm_pct:
                        stop=max(stop,r['entry_price']+(r['entry_fee']+fee(r['filled_qty'],True))/r['filled_qty'])
                    if reason is None:
                        if price<=stop:reason='STOP'
                        elif price>=r['target_price']:reason='TARGET'
                        elif s.checkpoint_seconds and age>=s.checkpoint_seconds and gain<=s.checkpoint_gain_pct:reason='PROGRESS'
                changes=dict(stop_price=stop,peak_bid=peak,pending_exit_reason=reason)
                if any(r.get(k)!=v for k,v in changes.items()):self.append('STATE',now,strategy_id=sid,setup_id=key,changes=changes)
            if not reason or mark is None:continue
            adjusted,book,error=self.book(sid,r['symbol'],q,'SELL',now)
            if error:continue
            d=classify_limit_order(adjusted,action='SELL',limit_price=float(q['bid']),requested_qty=r['remaining_qty'],now=now,max_quote_age_ms=s.max_quote_age_ms)
            if d.outcome not in {'FULL','PARTIAL'}:continue
            qty=d.filled_qty;price=mark['bid'];cost=fee(qty,True);book['used']+=qty
            pnl=qty*(price-r['entry_price'])-cost
            row=self.append('FILL',now,strategy_id=sid,setup_id=key,qty=qty,price=price,fee=cost,
                proceeds=qty*price-cost,pnl=pnl,exit_reason=reason,quote=dict(q),book=book,
                final=qty==r['remaining_qty'],entry_timestamp=r['timestamp'])
            closed.append(dict(row,symbol=r['symbol']))
        # The runner polls every five seconds. Bound durable account frames to
        # one per minute unless a fill requires immediate accounting visibility.
        if closed or self.last_snapshot_time is None or (now-self.last_snapshot_time).total_seconds()>=60:
            self.snapshot(quotes,now);self.status()
        return closed

    def snapshot(self,quotes,now):
        day=now.astimezone(g.NY).date().isoformat();accounts={};states={}
        for sid in sorted(IDS):
            if now<_utc(self.births[sid]):continue
            positions=[r for r in self.active.values() if r['strategy_id']==sid]
            marks=[mark_position(r,quotes.get(r['symbol']),now,g.SPECS[sid]) for r in positions]
            observed=self.observed.get(sid,{}).get('day')==day and self.observed[sid].get('ready_windows',0)>0
            equity=None if not observed or any(m is None for m in marks) else self.cash[sid]+sum(m['liquidation_value'] for m in marks)
            previous=self.state.get(sid,{})
            new_day=previous.get('day')!=day
            # A prior EOD mark is required if residuals cross midnight.
            start=(previous.get('last_equity') if positions and previous.get('last_equity') is not None else self.cash[sid]) if new_day else previous.get('day_start_equity')
            if new_day and positions:start=None
            peak=max(previous.get('peak',5000.),equity if equity is not None else 0.)
            dd=max(previous.get('max_drawdown_pct',0.),(peak-equity)/peak*100 if equity is not None and peak else 0.)
            state=dict(day=day,day_start_equity=start,peak=peak,max_drawdown_pct=dd,
                last_equity=equity,unknown=equity is None,drawdown_incomplete=previous.get('drawdown_incomplete',False) or equity is None and bool(positions))
            accounts[sid]=dict(equity=equity,cash=self.cash[sid],open_positions=len(positions),
                daily_pnl=equity-start if equity is not None and start is not None else None,
                daily_return_pct=(equity-start)/50 if equity is not None and start is not None else None,
                cumulative_return_pct=(equity/5000-1)*100 if equity is not None else None,
                max_drawdown_pct=dd,drawdown_incomplete=state['drawdown_incomplete'],
                realized_pnl=self.cash[sid]+sum(r['remaining_qty']*r['entry_price'] for r in positions)-5000.,
                unrealized_hypothetical_close_pnl=None if any(m is None for m in marks) else sum(m['unrealized_pnl'] for m in marks),
                completed=self.completed[sid],rejected=self.rejections[sid],
                status='mark_unavailable' if positions and equity is None else 'scanner_unobserved' if not observed else 'no_trades' if not positions and not self.completed[sid] and self.cash[sid]==5000 else 'prospective')
            states[sid]=state
        self.append('SNAPSHOT',now,accounts=accounts,drawdown_state=states)

    def status(self):
        atomic(self.root/(FILE_STEM+'_status.json'),dict(updated_at=_utc(self.clock()).isoformat(),population=722,
            population_hash=g.POPULATION_HASH,known_births=len(self.births),active=len(self.active),completed=sum(self.completed.values()),
            rejected=sum(self.rejections.values()),rejection_reasons=dict(self.reasons),sequence=self.seq,
            paper_only=True,broker_execution_enabled=False,shorting_enabled=False,
            execution_version=EXECUTION_VERSION,source_hashes=source_hashes(),accounts=self.snapshots,
            quote_freshness_enforced=True,displayed_liquidity_enforced=True,starting_cash=5000.,
            max_position_fraction=.2,capital_model='independent cumulative cash; no daily reset',
            costs='per-spec adverse slippage; 0.005/share min .01/side; sell .0002/share assumed',
            historical_backfill_enabled=False,portfolio_combinable=False))


def safe_call(tracker,method,*args):
    """Latch G11 faults without interrupting unrelated strategy workers.

    The error is durable and production verification fails until a healthy
    restart supersedes it. Never reset provenance to recover automatically.
    """
    if tracker is None or getattr(tracker,'failed',False):return False
    try:return getattr(tracker,method)(*args)
    except Exception as exc:
        tracker.failed=True
        error=dict(timestamp=datetime.now(timezone.utc).isoformat(),method=method,
                   error_type=type(exc).__name__,message=str(exc),paper_only=True)
        atomic(tracker.root/(FILE_STEM+'_error.json'),error)
        print('GENERATION_ELEVEN_FAILED_CLOSED '+json.dumps(error),flush=True)
        return False


def start_tracker(root,**kwargs):
    try:return GenerationElevenTracker(root,**kwargs)
    except Exception as exc:
        error=dict(timestamp=datetime.now(timezone.utc).isoformat(),method='initialize',
                   error_type=type(exc).__name__,message=str(exc),paper_only=True)
        atomic(Path(root)/(FILE_STEM+'_error.json'),error)
        print('GENERATION_ELEVEN_FAILED_CLOSED '+json.dumps(error),flush=True)
        return None
