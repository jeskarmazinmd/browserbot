"""STLEAD1: dynamically discover lagged relationships and trade follower underreaction."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="STLEAD1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def _corr(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;va=sum((x-ma)**2 for x in a);vb=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/(va*vb)**.5 if n>10 and va>0 and vb>0 else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=60));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  names=[s for s in q if len(self.h[s])>=46];best=None
  for leader in names:
   lr=_r(list(self.h[leader])[-46:]);last=lr[-1] if lr else 0
   if abs(last)<.12:continue
   for follower in names:
    if follower==leader:continue
    fr=_r(list(self.h[follower])[-46:]);lag=_corr(lr[:-1],fr[1:]);flast=fr[-1] if fr else 0
    if lag<.35 or last*flast<0 or abs(flast)>abs(last)*.65:continue
    score=lag*(abs(last)-abs(flast))
    if best is None or score>best[0]:best=(score,leader,follower,lag,last,flast)
  if not best:return []
  _,leader,follower,lag,lret,fret=best;fside="LONG" if lret>0 else "SHORT";lside="SHORT" if lret>0 else "LONG";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":follower,"side":fside,"bid":float(q[follower]["bid"]),"ask":float(q[follower]["ask"]),"weight":1},{"symbol":leader,"side":lside,"bid":float(q[leader]["bid"]),"ask":float(q[leader]["ask"]),"weight":1}],"target_pct":.45,"stop_pct":.40,"max_hold_minutes":90,"research":{"leader":leader,"follower":follower,"lagged_correlation":lag,"leader_last_return_pct":lret,"follower_last_return_pct":fret},"paper_only":True,"live_order_placement":False}]
