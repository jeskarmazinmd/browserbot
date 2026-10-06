"""Read-only G3 evidence audit. Never writes to source data or trading switches."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
CELL = re.compile(r'^[+-]?\d+(?:\.\d+)?%$')

def number(x):
    try:
        value = float(x)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def parse_table(text):
    """Handle raw daily histories and numbered terminal pastes, retaining gaps."""
    dates, rows = [], {}
    for line in text.replace('\\', '').splitlines():
        parts = line.split()
        if 'Module' in parts:
            tail = parts[parts.index('Module') + 1:]
            proposed = [p for p in tail if re.fullmatch(r'\d{2}-\d{2}|\d{4}-\d{2}-\d{2}', p)]
            if proposed:
                dates = proposed
            continue
        if not dates or not parts:
            continue
        if parts[0].isdigit():
            parts = parts[1:]
        if len(parts) not in (len(dates) + 1, len(dates) + 2):
            continue
        cells = parts[1:1 + len(dates)]
        if all(c == '-' or CELL.fullmatch(c) for c in cells):
            rows[parts[0]] = {d: None if c == '-' else float(c[:-1]) for d, c in zip(dates, cells)}
    return dates, rows

def summarize(values):
    present = [v for v in values if v is not None]
    if not present:
        return dict(observed_sessions=0, missing_sessions=len(values), sum_pct=None,
                    mean_pct=None, positive_sessions=0, negative_sessions=0,
                    max_drawdown_additive_pct=None, excluding_best_session_pct=None)
    cumulative = peak = drawdown = 0.0
    for v in present:
        cumulative += v
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return dict(observed_sessions=len(present), missing_sessions=len(values)-len(present),
                sum_pct=sum(present), mean_pct=statistics.mean(present),
                positive_sessions=sum(v > 0 for v in present), negative_sessions=sum(v < 0 for v in present),
                std_pct=statistics.stdev(present) if len(present) > 1 else None,
                best_session_pct=max(present), worst_session_pct=min(present),
                max_drawdown_additive_pct=drawdown,
                excluding_best_session_pct=sum(present)-max(present))

def pair_stats(a, b):
    pairs = [(a[d], b[d]) for d in a.keys() & b.keys() if a[d] is not None and b[d] is not None]
    if len(pairs) < 3:
        return None
    x, y = zip(*pairs)
    sx, sy = statistics.pstdev(x), statistics.pstdev(y)
    corr = sum((u-statistics.mean(x))*(v-statistics.mean(y)) for u,v in pairs)/len(pairs)/sx/sy if sx and sy else None
    return {'overlap_sessions':len(pairs), 'correlation':corr,
            'identical_rounded_path':all(u == v for u,v in pairs)}

def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text('')
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def audit_tables(paths, out):
    evidence = []
    recent = {}
    for path in paths:
        dates, modules = parse_table(path.read_text(errors='replace'))
        if not modules:
            continue
        for sid, daily in modules.items():
            row = {'source':path.name, 'module':sid, 'dates':','.join(dates), **summarize(list(daily.values()))}
            row.update({d:v for d,v in daily.items()})
            evidence.append(row)
        if path.name == 'recent_snapshot.txt':
            recent = modules
    write_csv(out/'daily_evidence.csv', evidence)
    if recent:
        # Reproduce the user's ranking for review only. Missing != verified zero.
        ordered = sorted(recent.items(), key=lambda item: sum(v or 0 for v in item[1].values()), reverse=True)
        ranked = [{'rank':i, 'module':sid, **summarize(list(daily.values())), **daily,
                   'retirement_status':'candidate_only_pending_full_history_and_dependency_audit' if i >= 300 else 'retain_pending_audit'}
                  for i,(sid,daily) in enumerate(ordered,1)]
        write_csv(out/'recent_all_modules.csv',ranked)
        write_csv(out/'bottom_154_candidates.csv',[r for r in ranked if r['rank'] >= 300])
        reference = recent.get('PMIDBA',{})
        write_csv(out/'pmid_daily_overlap.csv',
                  ({'module':sid, **stats} for sid, daily in recent.items() if (stats:=pair_stats(reference,daily))))
    return evidence

def stamp(value):
    try:
        ts = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return ts if ts.tzinfo else None
    except (ValueError,TypeError):
        return None

def lines(path):
    with path.open(errors='replace') as handle:
        yield from handle

def audit_ledger(path):
    """Keep each execution generation separate; cumulative exits are differenced."""
    entries, terminal, exit_rows = {}, {}, defaultdict(list)
    rejected, malformed, duplicates = Counter(), 0, 0
    seen = set()
    counts = defaultdict(Counter)
    for lineno,line in enumerate(lines(path),1):
        try:
            r = json.loads(line)
            if not isinstance(r,dict):
                raise ValueError()
        except (ValueError,TypeError):
            malformed += 1
            continue
        identity = hashlib.sha256(line.strip().encode()).hexdigest()
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        sid = r.get('strategy_id') or r.get('module_id')
        setup = r.get('setup_id') or r.get('group_id')
        event = str(r.get('event_type','')).upper()
        event = {'FAMILY_ENTRY':'PAPER_ENTRY', 'FAMILY_EXIT':'PAPER_EXIT',
                 'MULTI_LEG_ENTRY':'PAPER_ENTRY', 'MULTI_LEG_EXIT':'PAPER_EXIT'}.get(event,event)
        if not sid or not setup:
            counts[str(sid)]['unrecognized_identity'] += 1
            continue
        key = (sid,setup)
        counts[sid][event] += 1
        if event == 'PAPER_ENTRY':
            if key in entries:
                counts[sid]['duplicate_entry_identity'] += 1
            entries[key] = r
        elif event in {'PAPER_EXIT','PAPER_PARTIAL_EXIT'}:
            exit_rows[key].append(r)
            if event == 'PAPER_EXIT':
                terminal[key] = r
        elif 'REJECT' in event or 'SKIP' in event:
            rejected[(sid,str(r.get('reason') or (r.get('execution') or {}).get('reason')))] += 1
    trades = []
    for (sid,setup),entry in entries.items():
        final = terminal.get((sid,setup))
        exits = exit_rows[(sid,setup)]
        px = number(entry.get('entry_price'))
        qty = number(entry.get('filled_qty'))
        notional = number(entry.get('notional',entry.get('paper_notional')))
        if qty is None and px and notional is not None:
            qty = notional/px
        t0 = stamp(entry.get('execution_entry_timestamp') or entry.get('entry_timestamp') or entry.get('signal_timestamp'))
        t1 = stamp((final or {}).get('exit_timestamp'))
        pnl = None
        if final:
            proceeds = number(final.get('realized_proceeds'))
            if proceeds is not None and px and qty is not None:
                pnl = proceeds - px*qty
            else:
                pnl = number(final.get('pnl'))
        bid,ask = number(entry.get('entry_bid')),number(entry.get('entry_ask'))
        exit_fill_qty = sum(number(r.get('exit_fill_qty')) or 0 for r in exits)
        signal_time = stamp(entry.get('signal_timestamp'))
        stop = number(entry.get('stop_price'))
        target = number(entry.get('target_price'))
        exit_price = number((final or {}).get('exit_price'))
        trades.append({'source':path.name,'module':sid,'setup_id':setup,'symbol':entry.get('symbol'),
                       'entry_time':t0.isoformat() if t0 else None,
                       'entry_day_et':t0.astimezone(NY).date().isoformat() if t0 else None,
                       'entry_minute_et':t0.astimezone(NY).hour*60+t0.astimezone(NY).minute if t0 else None,
                       'exit_time':t1.isoformat() if t1 else None,'closed':bool(final),
                       'hold_seconds':(t1-t0).total_seconds() if t0 and t1 else None,
                       'entry_price':px,'filled_qty':qty,'requested_qty':entry.get('requested_qty'),
                       'entry_delay_seconds':(t0-signal_time).total_seconds() if t0 and signal_time else None,
                       'target_upside_pct':(target/px-1)*100 if target and px else None,
                       'stop_distance_pct':(1-stop/px)*100 if stop and px else None,
                       'exit_price':exit_price,
                       'exit_return_pct':(exit_price/px-1)*100 if exit_price and px else None,
                       'stop_overshoot_pct':(stop-exit_price)/px*100 if stop and px and exit_price and (final or {}).get('exit_reason')=='STOP' else None,
                       'entry_spread_pct':(ask/bid-1)*100 if bid and ask else None,
                       'quote_age_ms':entry.get('entry_quote_age_ms'),
                       'partial_exit_events':sum(r.get('event_type')=='PAPER_PARTIAL_EXIT' for r in exits),
                       'exit_reason':(final or {}).get('exit_reason'),
                       'closed_pnl':pnl,'cash_impact_of_extra_5bps_each_side':px*qty*.001 if px and qty else None,
                       'exit_quantity_mismatch':bool(exits and exit_fill_qty and qty is not None and exit_fill_qty > qty+1e-8)})
    summaries = []
    for sid,c in counts.items():
        own = [t for t in trades if t['module']==sid]
        closed = [t for t in own if t['closed'] and t['closed_pnl'] is not None]
        pnls = [t['closed_pnl'] for t in closed]
        positive = sum(p for p in pnls if p > 0)
        loss = -sum(p for p in pnls if p < 0)
        by_symbol = defaultdict(float)
        by_day = defaultdict(float)
        for t in closed:
            by_symbol[t['symbol']] += t['closed_pnl']
            by_day[t['entry_day_et']] += t['closed_pnl']
        top = max(by_symbol.values(),default=0)
        summaries.append({'source':path.name,'module':sid,'entries':len(own),'closed':len(closed),
                          'open':sum(not t['closed'] for t in own),'closed_pnl':sum(pnls),
                          'win_fraction':sum(p>0 for p in pnls)/len(pnls) if pnls else None,
                          'profit_factor':positive/loss if loss else None,
                          'unique_symbols':len({t['symbol'] for t in own}),
                          'closed_entry_days':len(by_day),'pnl_excluding_best_symbol':sum(pnls)-top,
                          'pnl_excluding_best_trade':sum(pnls)-max(pnls) if pnls else None,
                          'pnl_excluding_best_day':sum(pnls)-max(by_day.values()) if by_day else None,
                          'closed_pnl_extra_5bps_each_side':sum(t['closed_pnl']-(t['cash_impact_of_extra_5bps_each_side'] or 0) for t in closed),
                          'rejections':sum(n for (s,_),n in rejected.items() if s==sid),
                          **dict(c)})
    return trades,summaries,[{'source':path.name,'module':sid,'reason':reason,'count':n} for (sid,reason),n in rejected.items()], {'source':path.name,'malformed_lines':malformed,'exact_duplicate_lines':duplicates,'orphan_exit_setups':sum(k not in entries for k in exit_rows)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--snapshots',type=Path)
    p.add_argument('--data',type=Path)
    p.add_argument('--out',required=True,type=Path)
    args = p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    paths = list(args.snapshots.glob('*.txt')) if args.snapshots else []
    if args.data:
        paths += list(args.data.glob('all_engine*history*.txt'))
    evidence = audit_tables(paths,args.out)
    trades,summaries,rejects,quality = [],[],[],[]
    if args.data:
        # Modern ledgers only. Archive twins are separate evidence, never pooled.
        for path in sorted(args.data.glob('*bidask*outcomes*.jsonl')):
            ts,ss,rs,qs = audit_ledger(path)
            trades.extend(ts); summaries.extend(ss); rejects.extend(rs); quality.append(qs)
    write_csv(args.out/'trade_behavior.csv',trades)
    write_csv(args.out/'ledger_module_metrics.csv',summaries)
    write_csv(args.out/'rejection_reasons.csv',rejects)
    (args.out/'quality.json').write_text(json.dumps({'daily_evidence_rows':len(evidence),'ledgers':quality,
        'limitations':['Daily percentages may be rounded and portfolios reset; sums are additive evidence, not compounded investment returns.',
                       'Open residuals excluded from closed-trade metrics; reconcile separately with contemporaneous BID marks.',
                       'Main reported returns can resize ledger fills through the 5k risk simulator; raw ledger PnL is a separate metric.',
                       'Correlation from five daily observations is descriptive only.',
                       'No eligibility for retirement or deployment inferred from this audit.']},indent=2))

if __name__ == '__main__':
    main()
