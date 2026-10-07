"""Age-aware advisory review. Never changes controls or deletes ledgers.

Input sessions must be independently verified complete; a leaderboard row
alone cannot certify data coverage. Confidence intervals are descriptive,
not proof of durable edge or calibrated sequential hypothesis tests.
"""
from datetime import date
import math
import random
import statistics as st

POLICY=dict(min_calendar_age_days=90,min_complete_sessions=60,
            min_closed_trades=100,min_traded_sessions=20,
            block_sessions=5,bootstrap_draws=5000,confidence=.95)

def review(evidence,as_of,*,protected=()):
    today=date.fromisoformat(as_of); out=[]
    for sid,item in sorted(evidence.items()):
        row=dict(strategy_id=sid,status='INSUFFICIENT_EVIDENCE',policy=POLICY,
                 retirement_authorized=False)
        base=sid[:-2] if sid.endswith('BA') else sid
        if sid in protected or base in protected:
            row['status']='PROTECTED';out.append(row);continue
        try: born=date.fromisoformat(item['birth_date'])
        except (KeyError,TypeError,ValueError):
            row['reason']='unknown_birth_date';out.append(row);continue
        age=(today-born).days; rows=[]; seen=set(); invalid=False
        for r in item.get('sessions',[]):
            try:
                day=date.fromisoformat(r['day']); ret=float(r['return_pct']); n=int(r['closed_trades'])
                if day in seen or not math.isfinite(ret) or n<0: raise ValueError('invalid session')
                seen.add(day)
                if born<=day<today and r.get('coverage_verified') is True and r.get('unmarked',0)==0 and r.get('residual_positions',0)==0:
                    rows.append((day,ret,n))
            except (KeyError,ValueError,TypeError): invalid=True
        rows.sort(); n=len(rows); trades=sum(r[2] for r in rows); traded=sum(r[2]>0 for r in rows)
        row.update(calendar_age_days=age,complete_sessions=n,closed_trades=trades,traded_sessions=traded)
        if invalid:
            row['reason']='invalid_or_duplicate_session';out.append(row);continue
        if age<90 or n<60 or trades<100 or traded<20:
            row['reason']='age_coverage_or_activity_floor_not_met';out.append(row);continue
        vals=[r[1] for r in rows]
        row.update(status='MATURE_REVIEW',mean_daily_return_pct=st.mean(vals),
                   first_half_mean_pct=st.mean(vals[:n//2]),second_half_mean_pct=st.mean(vals[n//2:]),
                   sum_daily_returns_pct=sum(vals),returns_are_daily_equal_start=True)
        # Resample fixed, nonoverlapping five-observation blocks to retain some
        # local dependence. Longer dependence, regime shifts and selection remain.
        blocks=[st.mean(vals[i:i+5]) for i in range(0,n-4,5)]
        rng=random.Random(4107)
        means=sorted(st.mean(rng.choices(blocks,k=len(blocks))) for _ in range(5000))
        upper=means[math.ceil(.95*len(means))-1]
        row['descriptive_block_bootstrap_upper95_pct']=upper
        if upper<0 and row['first_half_mean_pct']<0 and row['second_half_mean_pct']<0:
            row['status']='NEGATIVE_REVIEW_CANDIDATE'
        row['limitations']='Advisory; unadjusted repeated/multiple comparisons; not a significance claim. Review complementarity, regimes, costs and dependencies before any separate retirement change.'
        out.append(row)
    return out


def main():
    import argparse,json
    from pathlib import Path
    from strategies.pruning import DEPENDENCY_PROTECTED_STRATEGY_IDS
    p=argparse.ArgumentParser(description='Advisory review for any generation; never applies retirement')
    p.add_argument('--evidence',required=True,type=Path)
    p.add_argument('--as-of',required=True)
    a=p.parse_args()
    evidence=json.loads(a.evidence.read_text())
    print(json.dumps(review(evidence,a.as_of,protected=DEPENDENCY_PROTECTED_STRATEGY_IDS|{'PMID'}),indent=2))

if __name__=='__main__':main()
