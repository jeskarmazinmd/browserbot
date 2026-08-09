"""CSDISP1: fade cross-sectional extremes only during unusually high dispersion."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="CSDISP1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=30));self.disp=deque(maxlen=60);self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  rows=[]
  for s,q in quotes.items():
   p=list(self.h[s]);
   if len(p)>=6 and p[-6]>0:rows.append(((p[-1]/p[-6]-1)*100,s,q))
  if len(rows)<100:return []
  d=statistics.pstdev(x[0] for x in rows);self.disp.append(d)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or len(self.disp)<15 or (self.last and (now-self.last).total_seconds()<1200):return []
  baseline=statistics.median(list(self.disp)[:-1]);rows.sort();lo,hi=rows[0],rows[-1]
  if baseline<=0 or d<baseline*1.5:return []
  self.last=now;out=[]
  for (ret,s,q),side in ((lo,"LONG"),(hi,"SHORT")):
   out.append({"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.55,"stop_pct":.42,"max_hold_minutes":60,"research":{"return_5m_pct":ret,"cross_section_dispersion_pct":d,"dispersion_baseline_pct":baseline,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False})
  return out
