"""Bear call credit spread when call wing volatility is unusually rich."""
from collections import defaultdict, deque
NAME="RVCALLCR1"; PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False; FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
H=defaultdict(lambda:deque(maxlen=36)); LAST={}
def _ok(x):
 b=float(x.get("bid") or 0);a=float(x.get("ask") or 0);m=(a+b)/2;return b>0 and a>=b and m>0 and (a-b)/m<=.10 and float(x.get("openInterest") or 0)>=100
def _pick(xs,d):return min(xs,key=lambda x:abs(float(x.get("delta") or 9)-d))
def evaluate(symbol,chain,now):
 calls=[x for x in chain if x.get("putCall")=="CALL" and 10<=x["daysToExpiration"]<=30 and _ok(x)];puts=[x for x in chain if x.get("putCall")=="PUT" and 10<=x["daysToExpiration"]<=30 and _ok(x)]
 if len(calls)<2 or not puts:return None
 e=min(x["expirationDate"] for x in calls);calls=[x for x in calls if x["expirationDate"]==e];puts=[x for x in puts if x["expirationDate"]==e]
 short=_pick(calls,.30);far=[x for x in calls if x["strikePrice"]>short["strikePrice"]];long=_pick(far,.15) if far else None
 if not long:return None
 metric=float(_pick(calls,.30)["volatility"])-float(_pick(puts,-.30)["volatility"]);h=H[symbol];trigger=len(h)>=12 and metric>sum(h)/len(h)+1.0;h.append(metric);day=now.date().isoformat()
 if not trigger or LAST.get(symbol)==day:return None
 credit=(short["bid"]-long["ask"])*100;width=(long["strikePrice"]-short["strikePrice"])*100
 if credit<=0 or credit>=width:return None
 LAST[symbol]=day;return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":width-credit+1.30,"target_return_pct":20,"stop_return_pct":35,"max_hold_minutes":360,"legs":[{**short,"side":"SELL","quantity":1},{**long,"side":"BUY","quantity":1}]}
