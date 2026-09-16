"""STHALF2: select residual spreads whose measured half-life fits the hold."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import math,statistics
STRATEGY_ID="STHALF2";FAMILY="STATARB2";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";PAIRS=(("SMH","QQQ"),("XLF","SPY"),("XLE","SPY"),("GLD","SLV"),("IYT","SPY"))
def metrics(a,b):
 n=min(len(a),len(b));a=a[-n:];b=b[-n:]
 if n<70:return None
 ma=sum(a)/n;mb=sum(b)/n;den=sum((x-mb)**2 for x in b);beta=sum((x-ma)*(y-mb) for x,y in zip(a,b))/den if den else 0;spread=[x-beta*y for x,y in zip(a,b)];m=statistics.fmean(spread);lag=[x-m for x in spread[:-1]];nxt=[x-m for x in spread[1:]];ld=sum(x*x for x in lag);phi=sum(x*y for x,y in zip(lag,nxt))/ld if ld else 2;half=-math.log(2)/math.log(phi) if 0<phi<1 else 999;sd=statistics.pstdev(spread);z=(spread[-1]-m)/sd if sd else 0;return beta,half,z
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=100));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  found=[]
  for a,b in PAIRS:
   if a in q and b in q:
    item=metrics(list(self.h[a]),list(self.h[b]))
    if item and .2<=item[0]<=3 and 4<=item[1]<=25 and abs(item[2])>=2:found.append((abs(item[2]),a,b,*item))
  if not found:return []
  _,a,b,beta,half,z=max(found);self.last=now;aside="SHORT" if z>0 else "LONG";bside="LONG" if z>0 else "SHORT"
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":a,"side":aside,"bid":float(q[a]["bid"]),"ask":float(q[a]["ask"]),"weight":1},{"symbol":b,"side":bside,"bid":float(q[b]["bid"]),"ask":float(q[b]["ask"]),"weight":beta}],"target_pct":.40,"stop_pct":.38,"max_hold_minutes":int(min(120,max(30,half*4))),"research":{"pair":[a,b],"hedge_ratio":beta,"half_life_minutes":half,"spread_z":z},"paper_only":True,"live_order_placement":False}]
