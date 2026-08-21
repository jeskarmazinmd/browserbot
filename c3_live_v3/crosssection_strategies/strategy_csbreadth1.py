"""CSBREADTH1: follow the strongest/weakest name during broad directional breadth."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="CSBREADTH1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=25));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
  rows=[]
  for s,q in quotes.items():
   p=list(self.h[s]);
   if len(p)>=6 and p[-6]>0:rows.append(((p[-1]/p[-6]-1)*100,s,q))
  if len(rows)<100:return []
  up=sum(x[0]>0 for x in rows)/len(rows);rows.sort();pick=None
  if up>=.72 and rows[-1][0]>=.35:pick=(rows[-1],"LONG")
  elif up<=.28 and rows[0][0]<=-.35:pick=(rows[0],"SHORT")
  if not pick:return []
  (ret,s,q),side=pick;self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.70,"stop_pct":.48,"max_hold_minutes":90,"research":{"return_5m_pct":ret,"positive_breadth":up,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False}]
