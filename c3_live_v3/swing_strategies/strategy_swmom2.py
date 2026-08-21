"""SWMOM2: two-session momentum continuation."""
from datetime import datetime,timezone
STRATEGY_ID="SWMOM2";FAMILY="SWING6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.last_day=None
 def evaluate(self,s):
  now=s["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or self.last_day==now.date():return []
  c=[]
  for sym,h in s.get("completed_daily_history",{}).items():
   q=s.get("quotes",{}).get(sym)
   if not q or len(h)<3:continue
   r=(float(h[-1][1])/float(h[-3][1])-1)*100;side="LONG" if r>=2 else ("SHORT" if r<=-2 else None)
   if side:c.append((abs(r),sym,q,side,r))
  if not c:return []
  _,sym,q,side,r=max(c);self.last_day=now.date();return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":sym,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":2.5,"stop_pct":1.6,"max_hold_sessions":2,"research":{"completed_2session_return_pct":r},"paper_only":True,"live_order_placement":False}]
