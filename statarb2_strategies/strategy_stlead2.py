"""STLEAD2: trade only leader-lag effects stable across adjacent windows."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="STLEAD2";FAMILY="STATARB2";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";PAIRS=(("QQQ","SMH"),("SMH","NVDA"),("XLF","JPM"),("SPY","IWM"),("GLD","SLV"))
def returns(p):return [(b/a-1)*100 for a,b in zip(p[:-1],p[1:]) if a>0]
def corr(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:];ma=sum(a)/n;mb=sum(b)/n;va=sum((x-ma)**2 for x in a);vb=sum((x-mb)**2 for x in b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/(va*vb)**.5 if n>10 and va and vb else 0
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=130));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  best=None
  for leader,follower in PAIRS:
   if leader not in q or follower not in q or len(self.h[leader])<101 or len(self.h[follower])<101:continue
   lr=returns(list(self.h[leader]));fr=returns(list(self.h[follower]));old=corr(lr[-101:-51],fr[-100:-50]);recent=corr(lr[-51:-1],fr[-50:]);impulse=sum(lr[-3:]);response=sum(fr[-3:])
   if min(old,recent)<.35 or abs(recent-old)>.25 or abs(impulse)<.15 or impulse*response<0 or abs(response)>abs(impulse)*.70:continue
   score=min(old,recent)*(abs(impulse)-abs(response))
   if best is None or score>best[0]:best=(score,leader,follower,old,recent,impulse,response)
  if not best:return []
  _,leader,follower,old,recent,impulse,response=best;self.last=now;fside="LONG" if impulse>0 else "SHORT";lside="SHORT" if impulse>0 else "LONG"
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":follower,"side":fside,"bid":float(q[follower]["bid"]),"ask":float(q[follower]["ask"]),"weight":1},{"symbol":leader,"side":lside,"bid":float(q[leader]["bid"]),"ask":float(q[leader]["ask"]),"weight":1}],"target_pct":.40,"stop_pct":.36,"max_hold_minutes":90,"research":{"leader":leader,"follower":follower,"older_lag_correlation":old,"recent_lag_correlation":recent,"relationship_drift":abs(recent-old),"leader_impulse_pct":impulse,"follower_response_pct":response},"paper_only":True,"live_order_placement":False}]
