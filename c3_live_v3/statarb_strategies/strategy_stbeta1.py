"""STBETA1: dynamic rolling-beta residual mean reversion versus SPY."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="STBETA1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _rets(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def _beta(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];mb=sum(b)/n;ma=sum(a)/n;v=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/v if n>5 and v>0 else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=70));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  spy=list(self.h["SPY"])
  if now<datetime.fromisoformat(FORWARD_START_UTC) or len(spy)<51 or (self.last and (now-self.last).total_seconds()<1800):return []
  sr=_rets(spy[-51:]);spy10=(spy[-1]/spy[-11]-1)*100;c=[]
  for s,x in q.items():
   if s=="SPY":continue
   p=list(self.h[s]);
   if len(p)<51:continue
   rr=_rets(p[-51:]);b=_beta(rr,sr)
   if not .2<=b<=2.5:continue
   resid=[u-b*v for u,v in zip(rr,sr)];sd=statistics.pstdev(resid) if len(resid)>10 else 0;own10=(p[-1]/p[-11]-1)*100;res=own10-b*spy10;z=res/(sd*(10**.5)) if sd>0 else 0
   if abs(z)>=2.0:c.append((abs(z),s,x,b,res,z))
  if not c:return []
  _,s,x,b,res,z=max(c);side="SHORT" if z>0 else "LONG";hedge="LONG" if side=="SHORT" else "SHORT";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":s,"side":side,"bid":float(x["bid"]),"ask":float(x["ask"]),"weight":1},{"symbol":"SPY","side":hedge,"bid":float(q["SPY"]["bid"]),"ask":float(q["SPY"]["ask"]),"weight":b}],"target_pct":.50,"stop_pct":.42,"max_hold_minutes":120,"research":{"rolling_beta":b,"residual_10m_pct":res,"residual_z":z},"paper_only":True,"live_order_placement":False}]
