"""CSVOLADJ1: volatility-normalized cross-sectional momentum."""
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics
STRATEGY_ID="CSVOLADJ1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=35));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1500):return []
  rows=[]
  for s,q in quotes.items():
   p=list(self.h[s]);
   if len(p)<16 or p[-11]<=0:continue
   one=[(b/a-1)*100 for a,b in zip(p[-16:-1],p[-15:]) if a>0];vol=statistics.pstdev(one) if len(one)>=10 else 0;ret=(p[-1]/p[-11]-1)*100
   if vol>.005:rows.append((ret/(vol*(10**.5)),ret,vol,s,q))
  if len(rows)<100:return []
  rows.sort();lo,hi=rows[0],rows[-1]
  if hi[0]<1.5 or lo[0]>-1.5:return []
  self.last=now;out=[]
  for x,side in ((hi,"LONG"),(lo,"SHORT")):
   score,ret,vol,s,q=x;out.append({"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.65,"stop_pct":.45,"max_hold_minutes":90,"research":{"vol_adjusted_score":score,"return_10m_pct":ret,"one_minute_vol_pct":vol,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False})
  return out
