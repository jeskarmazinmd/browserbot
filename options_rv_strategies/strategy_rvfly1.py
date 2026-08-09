"""Long call butterfly when the ATM body is rich relative to its wings."""
from collections import defaultdict,deque
NAME="RVFLY1";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";H=defaultdict(lambda:deque(maxlen=36));LAST={}
def _ok(x):
 b=float(x.get("bid") or 0);a=float(x.get("ask") or 0);m=(a+b)/2;return b>0 and a>=b and m>0 and (a-b)/m<=.10 and float(x.get("openInterest") or 0)>=100
def evaluate(symbol,chain,now):
 c=sorted([x for x in chain if x.get("putCall")=="CALL" and 14<=x["daysToExpiration"]<=30 and _ok(x)],key=lambda x:x["strikePrice"])
 if len(c)<5:return None
 e=min(x["expirationDate"] for x in c);c=[x for x in c if x["expirationDate"]==e];body=min(c,key=lambda x:abs(float(x.get("delta") or 9)-.50));i=c.index(body)
 if i<1 or i>=len(c)-1:return None
 low,high=c[i-1],c[i+1]
 if abs((body["strikePrice"]-low["strikePrice"])-(high["strikePrice"]-body["strikePrice"]))>.01:return None
 metric=float(body["volatility"])-(float(low["volatility"])+float(high["volatility"]))/2;h=H[symbol];trigger=len(h)>=12 and metric>sum(h)/len(h)+.5;h.append(metric);day=now.date().isoformat()
 if not trigger or LAST.get(symbol)==day:return None
 debit=(low["ask"]+high["ask"]-2*body["bid"])*100+2.60
 if debit<=0:return None
 LAST[symbol]=day;return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":debit,"target_return_pct":20,"stop_return_pct":30,"max_hold_minutes":360,"legs":[{**low,"side":"BUY","quantity":1},{**body,"side":"SELL","quantity":2},{**high,"side":"BUY","quantity":1}]}
