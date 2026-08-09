"""CSOPEN1: cross-sectional gap continuation during the first hour."""
from collections import defaultdict,deque
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
STRATEGY_ID="CSOPEN1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00";NY=ZoneInfo("America/New_York")
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=20));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  et=now.astimezone(NY);minute=et.hour*60+et.minute
  if now<datetime.fromisoformat(FORWARD_START_UTC) or not 575<=minute<=630 or (self.last and (now-self.last).total_seconds()<1200):return []
  rows=[]
  for s,q in quotes.items():
   p=list(self.h[s]);close=float(q.get("close") or 0)
   if len(p)>=4 and close>0 and p[-4]>0:
    gap=(p[-1]/close-1)*100;move=(p[-1]/p[-4]-1)*100;rows.append((gap,move,s,q))
  if len(rows)<100:return []
  rows.sort(key=lambda x:x[0]);lo,hi=rows[0],rows[-1];picks=[]
  if hi[0]>=1 and hi[1]>=.05:picks.append((hi,"LONG"))
  if lo[0]<=-1 and lo[1]<=-.05:picks.append((lo,"SHORT"))
  if not picks:return []
  self.last=now;out=[]
  for (gap,move,s,q),side in picks:
   out.append({"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.80,"stop_pct":.55,"max_hold_minutes":120,"research":{"gap_vs_prior_close_pct":gap,"recent_3m_move_pct":move,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False})
  return out
