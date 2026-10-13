"""Freeze live books before ledger scans; historical books must predate cutoff."""
import csv,gzip,json
from pathlib import Path
from datetime import datetime
from executable_paper_engine import executable_mark

def frozen_books(root,day,cutoff):
    root=Path(root);result={}
    path=root/'live_l1_snapshot.json'
    if path.exists():
        try:
            data=json.loads(path.read_text());observed=datetime.fromisoformat(data['collector_observed_at'])
            if observed<=cutoff and observed.date()==cutoff.date():result=data.get('quotes',{})
        except (ValueError,KeyError,TypeError):pass
    # Never consult a later live snapshot for a historical residual.
    if not result:
        compact=day.replace('-','')
        for path in sorted((root/'research_market').glob('*'+compact+'*.csv.gz')):
            try:
                with gzip.open(path,'rt') as f:
                    for row in csv.DictReader(f):
                        try:
                            observed=datetime.fromisoformat(row['observed_at_utc'])
                            if observed>cutoff:continue
                            q={k:float(v) for k,v in row.items() if k in {'bid','ask','bid_time_ms','ask_time_ms','quote_time_ms','bid_size_raw','ask_size_raw'} and v not in {'','None'}}
                            q['realtime']=row.get('realtime','').lower()=='true';q['collector_observed_at']=row['observed_at_utc']
                            old=result.get(row['symbol']);old_time=datetime.fromisoformat(old['collector_observed_at']) if old else None
                            if old_time is None or observed>=old_time:result[row['symbol']]=q
                        except (ValueError,KeyError,TypeError):continue
            except (OSError,EOFError):continue
    return result

def fresh_bid(quote,cutoff,age=5000):
    m=executable_mark(quote,action='SELL',now=cutoff,max_quote_age_ms=age)
    return quote if m['state']=='EXECUTABLE' and m.get('quote_age_ms',-1)>=0 else {}
