"""Isolated G8 cash, risk and timestamped book accounts; paper only, one writer."""
import fcntl
import hashlib
import json
import math
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from executable_paper_engine import executable_mark
from generation_two_paper_tracker import GenerationTwoBidAskTracker
from paper_outcome_tracker import _utc, NY
from strategies import generation_eight as g

FILE_STEM='paper_generation_eight_bidask_independent'
IDS=g.ALL_IDS

class GenerationEightBidAskTracker(GenerationTwoBidAskTracker):
    IDS=IDS
    FILE_STEM=FILE_STEM
    flash_catalog=g
    minute_catalog=g
    EXECUTION_MODEL='GENERATION_EIGHT_BIDASK_V1'

    def __init__(self,data_root,**kwargs):
        root=Path(data_root);root.mkdir(parents=True,exist_ok=True)
        self._writer=(root/(FILE_STEM+'_writer.lock')).open('a')
        try:fcntl.flock(self._writer.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self._writer.close();raise ValueError('G8 account already has a writer')
        self._last_admitted={};self._last_stopped={};self._stopped=set();self._stop_count=defaultdict(int)
        self._daily_realized=defaultdict(float);self._braked=set();self._carry_days=set();self._risk_quotes={}
        self._entry_quote=None;self._exit_quotes={};self._fill_now=None
        manifest=root/(FILE_STEM+'_manifest.json');birth=root/(FILE_STEM+'_births.json');ledger=root/(FILE_STEM+'_outcomes.jsonl')
        frozen=dict(rule_version=g.RULE_VERSION,population_hash=g.POPULATION_HASH,rule_source_sha256=g.RULE_SOURCE_SHA256,
                    tracker_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),population=120)
        try:
            if manifest.exists() and json.loads(manifest.read_text())!=frozen:raise ValueError('G8 frozen source changed; use new IDs')
            if (manifest.exists() or birth.exists() or (ledger.exists() and ledger.stat().st_size)) and (not manifest.exists() or not birth.exists()):raise ValueError('G8 provenance incomplete; refuse reset')
            self._verified_births=json.loads(birth.read_text()) if birth.exists() else {}
            if birth.exists() and set(self._verified_births)!=IDS:raise ValueError('G8 birth population differs')
            kwargs.update(eod_hour=15,eod_minute=50,entry_start_hour=10,entry_start_minute=30,entry_cutoff_hour=15,entry_cutoff_minute=30)
            super().__init__(root,**kwargs)
            self._atomic_json(manifest,frozen);self.ledger_path.touch(exist_ok=True)
            self.observation_path=root/(FILE_STEM+'_observations.json')
            self.observations=json.loads(self.observation_path.read_text()) if self.observation_path.exists() else {}
            self._atomic_json(self.observation_path,self.observations)
        except BaseException:
            self.close();raise

    def close(self):
        if getattr(self,'_writer',None) is not None and not self._writer.closed:
            fcntl.flock(self._writer.fileno(),fcntl.LOCK_UN);self._writer.close()

    def _cash_for(self,sid,now):
        d=now.astimezone(NY).date().isoformat()
        if any(r['strategy_id']==sid and _utc(r['entry_timestamp']).astimezone(NY).date().isoformat()<d for r in self.active.values()):
            self._carry_days.add((sid,d))
        return super()._cash_for(sid,now)

    def _apply_risk_row(self,row):
        sid=row['strategy_id'];event=row.get('event_type')
        if event=='PAPER_RISK_BRAKE':self._braked.add((sid,row['market_day']));return
        if event=='PAPER_ENTRY':self._last_admitted[(sid,row['symbol'])]=_utc(row['entry_timestamp'])
        if event in {'PAPER_PARTIAL_EXIT','PAPER_EXIT'}:
            when=_utc(row['exit_timestamp']);d=when.astimezone(NY).date().isoformat()
            self._daily_realized[(sid,d)]+=row['exit_fill_qty']*(row['exit_fill_price']-row['entry_price'])
            if 'STOP' in row.get('exit_reason',''):
                self._last_stopped[(sid,row['symbol'])]=when
                if row['setup_id'] not in self._stopped:
                    self._stopped.add(row['setup_id']);self._stop_count[(sid,row['symbol'],d)]+=1

    def _recover_rows(self,handle):
        open_qty={};book_used={}
        def checked():
            for line in handle:
                try:
                    r=json.loads(line);sid=r['strategy_id'];event=r['event_type']
                    if sid not in IDS or r.get('paper_only') is not True or r.get('broker_execution_enabled') is not False or r.get('live_order_placement') is not False:raise ValueError('paper contract')
                    if event in {'PAPER_ENTRY','PAPER_PARTIAL_EXIT','PAPER_EXIT'}:
                        if sid not in self._verified_births or _utc(r['signal_timestamp'])<_utc(self._verified_births[sid]):raise ValueError('prebirth fill')
                        k=r['setup_id'];qty=r['filled_qty'];phase='entry' if event=='PAPER_ENTRY' else 'exit'
                        if event=='PAPER_ENTRY':
                            if k in open_qty:raise ValueError('duplicate entry')
                            if qty<1 or abs(r['notional']-qty*r['entry_price'])>1e-6:raise ValueError('entry arithmetic')
                            open_qty[k]=qty
                        else:
                            if k not in open_qty or r['exit_fill_qty']<1 or r['exit_fill_qty']>open_qty[k]:raise ValueError('orphan/duplicate exit')
                            open_qty[k]-=r['exit_fill_qty']
                            if open_qty[k]!=r['remaining_qty']:raise ValueError('residual quantity mismatch')
                        q=r['execution_evidence'];side='ask' if phase=='entry' else 'bid';when=_utc(r['entry_timestamp'] if phase=='entry' else r['exit_timestamp'])
                        mark=executable_mark(q,action='BUY' if phase=='entry' else 'SELL',now=when,max_quote_age_ms=1000 if phase=='entry' else 5000)
                        if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0 or q.get('realtime') is not True:raise ValueError('nonexecutable historical fill')
                        px=r['entry_price'] if phase=='entry' else r['exit_fill_price']
                        if abs(px-q[side])>1e-6:raise ValueError('fill not at recorded book')
                        book=r['book_consumption'];key=(book['key'],tuple(book['identity']));prior=book_used.get(key,0)
                        filled=qty if phase=='entry' else r['exit_fill_qty'];cap=math.floor(float(q.get(side+'_size_raw',q.get(side+'_size',0)))*.1)
                        if book['used']!=prior+filled or book['used']>cap:raise ValueError('reused/excess book')
                        book_used[key]=book['used']
                    elif event not in {'PAPER_ENTRY_REJECTED','PAPER_RISK_BRAKE'}:raise ValueError('unknown event')
                    self._apply_risk_row(r)
                except (ValueError,KeyError,TypeError) as exc:raise ValueError('G8 corrupt ledger; preserve and review') from exc
                yield line
        super()._recover_rows(checked())

    def _append(self,row):
        row.update(paper_only=True,broker_execution_enabled=False,live_order_placement=False)
        q=self._entry_quote if row.get('event_type')=='PAPER_ENTRY' else self._exit_quotes.get(row.get('symbol'))
        if q is not None:
            row['execution_evidence']={k:q.get(k) for k in ('bid','ask','bid_size_raw','ask_size_raw','bid_size','ask_size','bid_time_ms','ask_time_ms','quote_time_ms','collector_observed_at','realtime')}
        if row.get('event_type')=='PAPER_ENTRY':row['recorded_at']=row['entry_timestamp']
        super()._append(row);self._apply_risk_row(row)

    def _write_status(self):
        super()._write_status();row=json.loads(self.status_path.read_text())
        row.update(generation=8,population=120,known_births=len(self.births),population_hash=g.POPULATION_HASH,
                   rule_version=g.RULE_VERSION,paper_only=True,live_order_placement=False,historical_backfill_enabled=False,
                   daily_equal_start_equity=5000.,risk_fraction=.01,max_symbol_fraction=.20,portfolio_risk_fraction=.02,
                   entry_quote_age_ms=1000,exit_quote_age_ms=5000,displayed_participation=.10,daily_loss_brake_pct=2.,
                   braked_accounts=len(self._braked),carry_unverified_accounts=len(self._carry_days))
        self._atomic_json(self.status_path,row)

    def _loss(self,sid,now):
        d=now.astimezone(NY).date().isoformat();pnl=self._daily_realized[(sid,d)]
        if (sid,d) in self._carry_days:return None
        for row in self.active.values():
            if row['strategy_id']!=sid:continue
            mark=executable_mark(self._risk_quotes.get(row['symbol']),action='SELL',now=now,max_quote_age_ms=5000)
            if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0:return None
            pnl+=row['remaining_qty']*(mark['price']-row['entry_price'])
        return pnl

    def _brake(self,sid,now):
        d=now.astimezone(NY).date().isoformat();key=(sid,d)
        if key in self._braked:return True
        loss=self._loss(sid,now)
        if loss is not None and loss<=-100.:
            self._append(dict(event_type='PAPER_RISK_BRAKE',strategy_id=sid,market_day=d,
                              setup_id=f'{sid}|RISK_BRAKE|{d}',recorded_at=now.isoformat(),verified_pnl=loss))
            return True
        return False

    def register_signal(self,signal,quote,now):
        sid=signal.get('strategy_id')
        if sid not in IDS:return False
        now=_utc(now);row=dict(signal);row.pop('setup_id',None)
        row['source_setup_id']=signal.get('setup_id');self._risk_quotes[row.get('symbol')]=dict(quote or {})
        ask=g_num((quote or {}).get('ask'))
        stop=g_num(row.get('g8_stop_pct'));target=g_num(row.get('g8_target_pct'))
        if not .4<=stop<=1.2 or not .6<=target<=2. or target+1e-10<stop*1.5:return False
        if ask>0:row.update(entry_price=ask,stop_price=ask*(1-stop/100),target_price=ask*(1+target/100))
        self._entry_quote=dict(quote or {})
        try:return super().register_signal(row,quote,now)
        finally:self._entry_quote=None

    def entry_gate(self,signal,quote,now):
        sid=signal['strategy_id'];s=g.spec_for(sid);symbol=signal['symbol'];d=now.astimezone(NY).date().isoformat()
        if signal.get('paper_only') is not True or signal.get('live_order_placement') is not False or signal.get('broker_execution_enabled') is not False:return 'g8_paper_contract'
        if any(signal.get(k)!=v for k,v in [('rule_version',g.RULE_VERSION),('population_hash',g.POPULATION_HASH),('rule_source_sha256',g.RULE_SOURCE_SHA256)]):return 'g8_frozen_rule_mismatch'
        t=g.timestamp(signal.get('timestamp'));minute=g.timestamp(signal.get('completed_minute'))
        if t is None or minute is None or minute.second or minute.microsecond or t!=minute+timedelta(minutes=1):return 'g8_completed_minute_provenance'
        if not g.time_admits(s,t) or not g.time_admits(s,now):return 'g8_execution_window'
        if signal.get('constituent_votes')!=[s.mechanism_code] or not g.admission_accepts(sid,signal.get('admission_evidence'),symbol):return 'g8_admission_evidence'
        if any(r['strategy_id']==sid and r['symbol']==symbol for r in self.active.values()):return 'g8_symbol_already_open'
        for mapping,seconds in [(self._last_admitted,s.cooldown_seconds),(self._last_stopped,s.stop_cooldown_seconds)]:
            last=mapping.get((sid,symbol))
            if last and (now-last).total_seconds()<seconds:return 'g8_symbol_cooldown'
        if self._stop_count[(sid,symbol,d)]>=2:return 'g8_two_stop_lockout'
        self._cash_for(sid,now)
        if (sid,d) in self._carry_days:return 'g8_carry_accounting_unknown'
        if self._brake(sid,now):return 'g8_daily_loss_brake'
        if self._loss(sid,now) is None:return 'g8_unverified_portfolio_marks'
        if (quote or {}).get('realtime') is not True:return 'g8_nonrealtime_quote'
        for action in ('BUY','SELL'):
            m=executable_mark(quote,action=action,now=now,max_quote_age_ms=1000)
            if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:return 'g8_nonexecutable_quote'
        ask,bid=float(quote['ask']),float(quote['bid']);target=float(signal['target_price'])
        if (ask/bid-1)*100>s.max_entry_spread_pct+1e-9:return 'g8_spread_limit'
        if (target/ask-1)*100<s.min_executable_upside_pct-1e-9:return 'g8_upside_geometry'
        if target-ask+1e-9<s.min_target_spread_multiple*(ask-bid):return 'g8_target_spread_multiple'
        return None

    def quantity_limit(self,sid,signal,ask,cash,requested):
        deployed=sum(r['remaining_qty']*r['entry_price'] for r in self.active.values() if r['strategy_id']==sid)
        symbol_deployed=sum(r['remaining_qty']*r['entry_price'] for r in self.active.values() if r['strategy_id']==sid and r['symbol']==signal['symbol'])
        equity=cash+deployed
        requested=min(requested,math.floor(min(cash,1000.,max(0,equity*.2-symbol_deployed))/ask))
        return super().quantity_limit(sid,signal,ask,cash,requested)

    def _available_book(self,sid,symbol,quote,action):
        adjusted,key,identity,used=super()._available_book(sid,symbol,quote,action)
        side='ask' if action=='BUY' else 'bid';size=g_num((quote or {}).get(side+'_size_raw',(quote or {}).get(side+'_size')))
        adjusted[side+'_size_raw']=min(g_num(adjusted.get(side+'_size_raw')),max(0,math.floor(size*.1)-used))
        return adjusted,key,identity,used

    def update_quotes(self,quotes,now):
        now=_utc(now);self._risk_quotes.update(quotes);self._exit_quotes=quotes
        for sid in {r['strategy_id'] for r in self.active.values()}:
            self._cash_for(sid,now);braked=self._brake(sid,now)
            for row in self.active.values():
                if row['strategy_id']!=sid or row.get('pending_exit_reason'):continue
                if braked:row['pending_exit_reason']='G8_DAILY_LOSS_BRAKE'
                elif (now-_utc(row['entry_timestamp'])).total_seconds()>=1800:row['pending_exit_reason']='G8_MAX_HOLD'
        filtered={s:q for s,q in quotes.items() if q.get('realtime') is True and (lambda m:m['state']=='EXECUTABLE' and m.get('quote_age_ms',-1)>=0)(executable_mark(q,action='SELL',now=now,max_quote_age_ms=5000))}
        try:return super().update_quotes(filtered,now)
        finally:self._exit_quotes={}

    def observe_snapshot(self,snapshot,*,current,errors=()):
        if not current:return
        t=_utc(snapshot.timestamp)+timedelta(minutes=1);bad={sid for sid,_ in errors}
        for s in g.CATALOG:
            if t<_utc(self.births[s.strategy_id]) or not g.time_admits(s,t):continue
            d=t.astimezone(NY).date().isoformat();row=self.observations.setdefault(s.strategy_id,{}).setdefault(d,dict(evaluated_minutes=0,error_minutes=0,last_minute=None))
            if row['last_minute'] and t<=_utc(row['last_minute']):continue
            row.update(evaluated_minutes=row['evaluated_minutes']+1,error_minutes=row['error_minutes']+int(s.strategy_id in bad),last_minute=t.isoformat())
        self._atomic_json(self.observation_path,self.observations)

def g_num(v):
    try:return float(v) if math.isfinite(float(v)) else 0.
    except (ValueError,TypeError):return 0.
