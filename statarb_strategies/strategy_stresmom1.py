"""STRESMOM1: follow residual momentum when a formerly correlated pair structurally decouples."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="STRESMOM1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def _corr(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;va=sum((x-ma)**2 for x in a);vb=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/(va*vb)**.5 if n>5 and va>0 and vb>0 else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=70));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  names=[s for s in q if len(self.h[s])>=51];best=None
  for i,a in enumerate(names):
   pa=list(self.h[a]);ra=_r(pa[-51:])
   for b in names[i+1:]:
    pb=list(self.h[b]);rb=_r(pb[-51:]);prior=_corr(ra[:-10],rb[:-10]);recent=_corr(ra[-10:],rb[-10:])
    if prior<.65 or recent>.25:continue
    a5=(pa[-1]/pa[-6]-1)*100;b5=(pb[-1]/pb[-6]-1)*100;res=a5-b5
    if abs(res)<.5:continue
    score=abs(res)*(prior-recent)
    if best is None or score>best[0]:best=(score,a,b,prior,recent,res)
  if not best:return []
  _,a,b,prior,recent,res=best;aside="LONG" if res>0 else "SHORT";bside="SHORT" if res>0 else "LONG";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":a,"side":aside,"bid":float(q[a]["bid"]),"ask":float(q[a]["ask"]),"weight":1},{"symbol":b,"side":bside,"bid":float(q[b]["bid"]),"ask":float(q[b]["ask"]),"weight":1}],"target_pct":.55,"stop_pct":.45,"max_hold_minutes":90,"research":{"pair":[a,b],"prior_correlation":prior,"recent_correlation":recent,"residual_5m_pct":res,"mode":"relationship_break_continuation"},"paper_only":True,"live_order_placement":False}]
