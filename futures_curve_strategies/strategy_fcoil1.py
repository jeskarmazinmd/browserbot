"""FCOIL1: mean-revert Micro WTI contango/backwardation shocks."""
from collections import deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="FCOIL1";FAMILY="FUTURES_CURVE6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-09T22:00:00+00:00";ROOT="/MCL";MODE="MEAN_REVERSION";Z_TRIGGER=1.5;MAX_COST=140.;TP=180.;SL=150.;HOLD=1440;MIN_HISTORY=24
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=deque(maxlen=96);self.contracts=None;self.last=None
 def evaluate(self,s):
  now=s["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);rows=s.get("curves",{}).get(ROOT,[])
  if now<datetime.fromisoformat(FORWARD_START_UTC) or len(rows)<2:return []
  a,b=rows[:2];pair=(a["symbol"],b["symbol"])
  if pair!=self.contracts:self.h.clear();self.contracts=pair
  am=(float(a["bid"])+float(a["ask"]))/2;bm=(float(b["bid"])+float(b["ask"]))/2;days=(float(b["expiration_ms"])-float(a["expiration_ms"]))/86400000
  if am<=0 or days<=0:return []
  carry=(bm/am-1)*100*365/days;self.h.append(carry)
  if len(self.h)<MIN_HISTORY or (self.last and (now-self.last).total_seconds()<21600):return []
  prior=list(self.h)[:-1];sd=statistics.pstdev(prior);z=(carry-statistics.mean(prior))/sd if sd>0 else 0;cost=sum((float(x["ask"])-float(x["bid"]))*float(x["multiplier"])+4.5 for x in (a,b))
  if abs(z)<Z_TRIGGER or cost>MAX_COST:return []
  self.last=now;deferred="SHORT" if z>0 else "LONG";front="LONG" if z>0 else "SHORT";legs=[{"symbol":a["symbol"],"side":front,"bid":a["bid"],"ask":a["ask"],"multiplier":a["multiplier"],"expiration":a["expiration_ms"]},{"symbol":b["symbol"],"side":deferred,"bid":b["bid"],"ask":b["ask"],"multiplier":b["multiplier"],"expiration":b["expiration_ms"]}]
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":legs,"take_profit_dollars":TP,"stop_loss_dollars":SL,"max_hold_minutes":HOLD,"research":{"annualized_carry_pct":carry,"carry_z":z,"minimum_roundtrip_cost_dollars":cost,"mode":MODE},"paper_only":True,"live_order_placement":False}]
