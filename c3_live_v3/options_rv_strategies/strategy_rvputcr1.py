"""Bull put credit spread when put skew is unusually rich."""
from collections import defaultdict, deque

NAME="RVPUTCR1"; PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
H=defaultdict(lambda: deque(maxlen=36)); LAST={}

def _ok(x):
    b=float(x.get("bid") or 0); a=float(x.get("ask") or 0); m=(a+b)/2
    return b>0 and a>=b and m>0 and (a-b)/m<=.10 and float(x.get("openInterest") or 0)>=100
def _pick(xs, target): return min(xs,key=lambda x:abs(float(x.get("delta") or 9)-target))
def evaluate(symbol, chain, now):
    puts=[x for x in chain if x.get("putCall")=="PUT" and 10<=x["daysToExpiration"]<=30 and _ok(x)]
    calls=[x for x in chain if x.get("putCall")=="CALL" and 10<=x["daysToExpiration"]<=30 and _ok(x)]
    if len(puts)<2 or not calls:return None
    expiry=min(x["expirationDate"] for x in puts); puts=[x for x in puts if x["expirationDate"]==expiry]; calls=[x for x in calls if x["expirationDate"]==expiry]
    short=_pick(puts,-.30); long=_pick([x for x in puts if x["strikePrice"]<short["strikePrice"]],-.15) if any(x["strikePrice"]<short["strikePrice"] for x in puts) else None
    if not long:return None
    atm_p=_pick(puts,-.50); atm_c=_pick(calls,.50); metric=float(atm_p["volatility"])-float(atm_c["volatility"])
    hist=H[symbol]; trigger=len(hist)>=12 and metric>sum(hist)/len(hist)+1.0; hist.append(metric)
    day=now.date().isoformat()
    if not trigger or LAST.get(symbol)==day:return None
    credit=(short["bid"]-long["ask"])*100; width=(short["strikePrice"]-long["strikePrice"])*100
    if credit<=0 or credit>=width:return None
    LAST[symbol]=day
    return {"setup_id":f"{NAME}:{symbol}:{day}","strategy_id":NAME,"underlying":symbol,"defined_risk":True,"max_loss_dollars":width-credit+1.30,"target_return_pct":20,"stop_return_pct":35,"max_hold_minutes":360,"legs":[{**short,"side":"SELL","quantity":1},{**long,"side":"BUY","quantity":1}]}
