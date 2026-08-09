"""SWTREND20: persistent twenty-session directional trend."""
from datetime import datetime,timezone
STRATEGY_ID="SWTREND20";FAMILY="SWING6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.last_day=None
 def evaluate(self,s):
  now=s["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or self.last_day==now.date():return []
  c=[]
  for sym,h in s.get("completed_daily_history",{}).items():
   q=s.get("quotes",{}).get(sym)
   if not q or len(h)<21:continue
   p=[float(x[1]) for x in h[-21:]];ret=(p[-1]/p[0]-1)*100;up=sum(b>a for a,b in zip(p,p[1:]))/20;side="LONG" if ret>=6 and up>=.6 else ("SHORT" if ret<=-6 and up<=.4 else None)
   if side:c.append((abs(ret)*(abs(up-.5)+.5),sym,q,side,ret,up))
  if not c:return []
  _,sym,q,side,ret,up=max(c);self.last_day=now.date();return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":sym,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":6,"stop_pct":3.5,"max_hold_sessions":10,"research":{"completed_20session_return_pct":ret,"up_session_fraction":up},"paper_only":True,"live_order_placement":False}]
