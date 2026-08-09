"""STBREAK1: mean-revert a sudden divergence in a previously stable rolling relationship."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="STBREAK1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def _corr(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;va=sum((x-ma)**2 for x in a);vb=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/(va*vb)**.5 if n>10 and va>0 and vb>0 else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=65));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  names=[s for s in q if len(self.h[s])>=51];best=None
  for i,a in enumerate(names):
   pa=list(self.h[a]);ra=_r(pa[-51:])
   for b in names[i+1:]:
    pb=list(self.h[b]);rb=_r(pb[-51:]);c=_corr(ra[:-5],rb[:-5])
    if c<.8:continue
    rel=[x-y for x,y in zip(ra[:-5],rb[:-5])];sd=statistics.pstdev(rel) if len(rel)>10 else 0;a3=(pa[-1]/pa[-4]-1)*100;b3=(pb[-1]/pb[-4]-1)*100;div=a3-b3;z=div/(sd*(3**.5)) if sd>0 else 0
    if abs(z)>=2.5 and (best is None or abs(z)*c>best[0]):best=(abs(z)*c,a,b,c,z,div)
  if not best:return []
  _,a,b,c,z,div=best;aside="SHORT" if z>0 else "LONG";bside="LONG" if z>0 else "SHORT";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":a,"side":aside,"bid":float(q[a]["bid"]),"ask":float(q[a]["ask"]),"weight":1},{"symbol":b,"side":bside,"bid":float(q[b]["bid"]),"ask":float(q[b]["ask"]),"weight":1}],"target_pct":.50,"stop_pct":.42,"max_hold_minutes":90,"research":{"pair":[a,b],"prior_correlation":c,"divergence_3m_pct":div,"divergence_z":z},"paper_only":True,"live_order_placement":False}]
