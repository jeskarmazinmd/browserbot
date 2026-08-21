"""Long call diagonal when deferred volatility is cheap versus the front wing."""
from collections import defaultdict,deque
NAME="RVDIAG1";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";H=defaultdict(lambda:deque(maxlen=36));LAST={}
def _ok(x):
 b=float(x.get("bid") or 0);a=float(x.get("ask") or 0);m=(a+b)/2;return b>0 and a>=b and m>0 and (a-b)/m<=.10 and float(x.get("openInterest") or 0)>=100
def _p(xs,d):return min(xs,key=lambda x:abs(float(x.get("delta") or 9)-d))
def evaluate(symbol,chain,now):
 c=[x for x in chain if x.get("putCall")=="CALL" and _ok(x) and 7<=x["daysToExpiration"]<=50];near=[x for x in c if x["daysToExpiration"]<=21];far=[x for x in c if x["daysToExpiration"]>=28]
 if not near or not far:return None
 sell=_p(near,.35);buy=_p(far,.55);metric=float(sell["volatility"])-float(buy["volatility"]);h=H[symbol];trigger=len(h)>=12 and metric>sum(h)/len(h)+.8;h.append(metric);day=now.date().isoformat()
 if not trigger or LAST.get(symbol)==day:return None
 debit=(buy["ask"]-sell["bid"])*100+1.30
 if debit<=0:return None
 LAST[symbol]=day;return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":debit,"target_return_pct":15,"stop_return_pct":25,"max_hold_minutes":360,"legs":[{**sell,"side":"SELL"},{**buy,"side":"BUY"}]}
