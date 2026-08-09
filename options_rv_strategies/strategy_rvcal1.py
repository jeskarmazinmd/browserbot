"""Long call calendar when near-term IV is rich versus deferred IV."""
from collections import defaultdict,deque
NAME="RVCAL1";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";H=defaultdict(lambda:deque(maxlen=36));LAST={}
def _ok(x):
 b=float(x.get("bid") or 0);a=float(x.get("ask") or 0);m=(a+b)/2;return b>0 and a>=b and m>0 and (a-b)/m<=.10 and float(x.get("openInterest") or 0)>=100
def _p(xs,d):return min(xs,key=lambda x:abs(float(x.get("delta") or 9)-d))
def evaluate(symbol,chain,now):
 calls=[x for x in chain if x.get("putCall")=="CALL" and _ok(x) and 7<=x["daysToExpiration"]<=50]
 near=[x for x in calls if x["daysToExpiration"]<=21];far=[x for x in calls if x["daysToExpiration"]>=28]
 if not near or not far:return None
 n=_p(near,.50);same=[x for x in far if x["strikePrice"]==n["strikePrice"]];f=min(same,key=lambda x:x["daysToExpiration"]) if same else None
 if not f:return None
 metric=float(n["volatility"])-float(f["volatility"]);h=H[symbol];trigger=len(h)>=12 and metric>sum(h)/len(h)+1.0;h.append(metric);day=now.date().isoformat()
 if not trigger or LAST.get(symbol)==day:return None
 debit=(f["ask"]-n["bid"])*100+1.30
 if debit<=0:return None
 LAST[symbol]=day;return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":debit,"target_return_pct":15,"stop_return_pct":25,"max_hold_minutes":360,"legs":[{**n,"side":"SELL"},{**f,"side":"BUY"}]}
