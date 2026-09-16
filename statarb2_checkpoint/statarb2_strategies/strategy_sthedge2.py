"""STHEDGE2: residual reversion only when short/long hedge ratios agree."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="STHEDGE2";FAMILY="STATARB2";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def rets(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def beta(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;den=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/den if n>10 and den else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=130));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  spy=list(self.h["SPY"])
  if now<datetime.fromisoformat(FORWARD_START_UTC) or len(spy)<101 or (self.last and (now-self.last).total_seconds()<1800):return []
  sr=rets(spy);best=None
  for s,x in q.items():
   if s=="SPY" or len(self.h[s])<101:continue
   rr=rets(list(self.h[s]));short=beta(rr[-30:],sr[-30:]);long=beta(rr[-100:],sr[-100:])
   if not .2<=long<=2.5 or abs(short-long)>.25:continue
   residual=[u-long*v for u,v in zip(rr[-60:],sr[-60:])];sd=statistics.pstdev(residual);recent=sum(residual[-10:]);z=recent/(sd*(10**.5)) if sd else 0
   if abs(z)>=2 and (best is None or abs(z)>abs(best[-1])):best=(s,x,long,short,z)
  if not best:return []
  s,x,long,short,z=best;self.last=now;side="SHORT" if z>0 else "LONG";hedge="LONG" if z>0 else "SHORT"
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":s,"side":side,"bid":float(x["bid"]),"ask":float(x["ask"]),"weight":1},{"symbol":"SPY","side":hedge,"bid":float(q["SPY"]["bid"]),"ask":float(q["SPY"]["ask"]),"weight":long}],"target_pct":.45,"stop_pct":.38,"max_hold_minutes":120,"research":{"long_beta":long,"short_beta":short,"beta_drift":abs(short-long),"residual_z":z},"paper_only":True,"live_order_placement":False}]
