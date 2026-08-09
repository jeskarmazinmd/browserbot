"""CSRELSPY1: long/short the largest ten-minute residuals versus SPY."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="CSRELSPY1";FAMILY="CROSSSECTION8";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=35));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);quotes=snapshot.get("quotes",{})
  for s,q in quotes.items():self.h[s].append((float(q["bid"])+float(q["ask"]))/2)
  spy=list(self.h["SPY"])
  if now<datetime.fromisoformat(FORWARD_START_UTC) or len(spy)<11 or (self.last and (now-self.last).total_seconds()<1500):return []
  spyret=(spy[-1]/spy[-11]-1)*100;rows=[]
  for s,q in quotes.items():
   if s=="SPY":continue
   p=list(self.h[s]);
   if len(p)>=11 and p[-11]>0:
    ret=(p[-1]/p[-11]-1)*100;rows.append((ret-spyret,ret,s,q))
  if len(rows)<100:return []
  rows.sort();lo,hi=rows[0],rows[-1]
  if hi[0]-lo[0]<.80:return []
  self.last=now;out=[]
  for x,side in ((hi,"LONG"),(lo,"SHORT")):
   residual,ret,s,q=x;out.append({"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.70,"stop_pct":.48,"max_hold_minutes":90,"research":{"return_10m_pct":ret,"spy_return_10m_pct":spyret,"residual_vs_spy_pct":residual,"ranked_symbols":len(rows)},"paper_only":True,"live_order_placement":False})
  return out
