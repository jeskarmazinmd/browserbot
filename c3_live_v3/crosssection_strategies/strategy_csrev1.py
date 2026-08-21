"""CSREV1: cross-sectional extreme mean reversion after a one-minute turn."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="CSREV1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=30));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
  rows=[]
  for s,q in quotes.items():
   p=list(self.h[s]);
   if len(p)>=11 and p[-11]>0 and p[-2]>0:rows.append(((p[-1]/p[-11]-1)*100,(p[-1]/p[-2]-1)*100,s,q))
  if len(rows)<100:return []
  rows.sort(key=lambda x:x[0]);low=next((x for x in rows[:max(5,len(rows)//20)] if x[1]>.03),None);high=next((x for x in reversed(rows[-max(5,len(rows)//20):]) if x[1]<-.03),None)
  if not low and not high:return []
  self.last=now;out=[]
  for x,side in ((low,"LONG"),(high,"SHORT")):
   if not x:continue
   r10,r1,s,q=x;out.append({"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.55,"stop_pct":.40,"max_hold_minutes":60,"research":{"return_10m_pct":r10,"turn_1m_pct":r1,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False})
  return out
