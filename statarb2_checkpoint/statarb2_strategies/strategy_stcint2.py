"""STCINT2: log-price residual reversion with a stationary-AR(1) gate."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import math,statistics
STRATEGY_ID="STCINT2";FAMILY="STATARB2";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
PAIRS=(("QQQ","SPY"),("AMD","NVDA"),("JPM","BAC"),("GLD","SLV"),("AAPL","MSFT"))
def fit(a,b):
 n=min(len(a),len(b));x=[math.log(v) for v in b[-n:]];y=[math.log(v) for v in a[-n:]];mx=sum(x)/n;my=sum(y)/n;den=sum((v-mx)**2 for v in x)
 if n<80 or den<=0:return None
 beta=sum((u-my)*(v-mx) for u,v in zip(y,x))/den;res=[u-(my-beta*mx)-beta*v for u,v in zip(y,x)];lag=res[:-1];change=[res[i]-res[i-1] for i in range(1,n)];ld=sum(v*v for v in lag)
 phi=1+(sum(v*d for v,d in zip(lag,change))/ld if ld else 0);sd=statistics.pstdev(res);z=(res[-1]-statistics.fmean(res))/sd if sd else 0;half=-math.log(2)/math.log(phi) if 0<phi<1 else 999
 return beta,phi,half,z
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=130));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  best=None
  for a,b in PAIRS:
   if a not in q or b not in q:continue
   item=fit(list(self.h[a]),list(self.h[b]));
   if not item:continue
   beta,phi,half,z=item
   if .05<=half<=35 and abs(z)>=2.1 and (best is None or abs(z)>abs(best[-1])):best=(a,b,beta,phi,half,z)
  if not best:return []
  a,b,beta,phi,half,z=best;self.last=now;aside="SHORT" if z>0 else "LONG";bside="LONG" if z>0 else "SHORT"
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":a,"side":aside,"bid":float(q[a]["bid"]),"ask":float(q[a]["ask"]),"weight":1},{"symbol":b,"side":bside,"bid":float(q[b]["bid"]),"ask":float(q[b]["ask"]),"weight":max(.2,min(2.5,beta))}],"target_pct":.45,"stop_pct":.40,"max_hold_minutes":120,"research":{"pair":[a,b],"log_hedge_ratio":beta,"ar1_phi":phi,"half_life_minutes":half,"residual_z":z},"paper_only":True,"live_order_placement":False}]
