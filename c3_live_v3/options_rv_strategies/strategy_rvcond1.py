"""Defined-risk iron condor when the liquid surface becomes unusually rich."""
from collections import defaultdict,deque
NAME="RVCOND1";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";H=defaultdict(lambda:deque(maxlen=36));LAST={}
def _ok(x):
 b=float(x.get("bid") or 0);a=float(x.get("ask") or 0);m=(a+b)/2;return b>0 and a>=b and m>0 and (a-b)/m<=.08 and float(x.get("openInterest") or 0)>=200
def _p(xs,d):return min(xs,key=lambda x:abs(float(x.get("delta") or 9)-d))
def evaluate(symbol,chain,now):
 xs=[x for x in chain if 14<=x["daysToExpiration"]<=30 and _ok(x)]
 if len(xs)<8:return None
 e=min(x["expirationDate"] for x in xs);p=[x for x in xs if x["expirationDate"]==e and x["putCall"]=="PUT"];c=[x for x in xs if x["expirationDate"]==e and x["putCall"]=="CALL"]
 if len(p)<2 or len(c)<2:return None
 ps=_p(p,-.20);pl=_p([x for x in p if x["strikePrice"]<ps["strikePrice"]],-.10) if any(x["strikePrice"]<ps["strikePrice"] for x in p) else None;cs=_p(c,.20);cl=_p([x for x in c if x["strikePrice"]>cs["strikePrice"]],.10) if any(x["strikePrice"]>cs["strikePrice"] for x in c) else None
 if not pl or not cl:return None
 metric=(float(_p(p,-.50)["volatility"])+float(_p(c,.50)["volatility"]))/2;h=H[symbol];trigger=len(h)>=12 and metric>sum(h)/len(h)*1.08;h.append(metric);day=now.date().isoformat()
 if not trigger or LAST.get(symbol)==day:return None
 credit=(ps["bid"]+cs["bid"]-pl["ask"]-cl["ask"])*100;width=max(ps["strikePrice"]-pl["strikePrice"],cl["strikePrice"]-cs["strikePrice"])*100
 if credit<=0 or credit>=width:return None
 LAST[symbol]=day;return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":width-credit+2.60,"target_return_pct":18,"stop_return_pct":30,"max_hold_minutes":360,"legs":[{**pl,"side":"BUY"},{**ps,"side":"SELL"},{**cs,"side":"SELL"},{**cl,"side":"BUY"}]}
