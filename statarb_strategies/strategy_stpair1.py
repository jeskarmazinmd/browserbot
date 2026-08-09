"""STPAIR1: discover the strongest rolling pair and fade standardized spread divergence."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="STPAIR1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def _corr(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;va=sum((x-ma)**2 for x in a);vb=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/(va*vb)**.5 if n>10 and va>0 and vb>0 else 0
def _beta(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;v=sum((y-mb)**2 for y in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/v if v>0 else 0
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
    pb=list(self.h[b]);rb=_r(pb[-51:]);c=_corr(ra,rb)
    if c<.75:continue
    beta=_beta(ra,rb)
    if not .2<=beta<=2.5:continue
    residuals=[x-beta*y for x,y in zip(ra,rb)];sd=statistics.pstdev(residuals);a5=(pa[-1]/pa[-6]-1)*100;b5=(pb[-1]/pb[-6]-1)*100;res=a5-beta*b5;z=res/(sd*(5**.5)) if sd>0 else 0
    score=abs(z)*c
    if abs(z)>=2 and (best is None or score>best[0]):best=(score,a,b,beta,c,z,res)
  if not best:return []
  _,a,b,beta,c,z,res=best;aside="SHORT" if z>0 else "LONG";bside="LONG" if z>0 else "SHORT";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":a,"side":aside,"bid":float(q[a]["bid"]),"ask":float(q[a]["ask"]),"weight":1},{"symbol":b,"side":bside,"bid":float(q[b]["bid"]),"ask":float(q[b]["ask"]),"weight":beta}],"target_pct":.50,"stop_pct":.42,"max_hold_minutes":120,"research":{"pair":[a,b],"rolling_correlation":c,"rolling_beta":beta,"spread_z":z,"residual_5m_pct":res},"paper_only":True,"live_order_placement":False}]
