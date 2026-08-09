"""SWBREAK10: live-price breakout beyond ten completed-session closes."""
from datetime import datetime,timezone
STRATEGY_ID="SWBREAK10";FAMILY="SWING6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.last_day=None
 def evaluate(self,s):
  now=s["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or self.last_day==now.date():return []
  c=[]
  for sym,h in s.get("completed_daily_history",{}).items():
   q=s.get("quotes",{}).get(sym)
   if not q or len(h)<10:continue
   prior=[float(x[1]) for x in h[-10:]];mid=(float(q["bid"])+float(q["ask"]))/2;hi=max(prior);lo=min(prior);up=(mid/hi-1)*100;dn=(mid/lo-1)*100;side="LONG" if up>=.5 else ("SHORT" if dn<=-.5 else None)
   if side:c.append((max(up,-dn),sym,q,side,up,dn))
  if not c:return []
  _,sym,q,side,up,dn=max(c);self.last_day=now.date();return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":sym,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":4,"stop_pct":2.3,"max_hold_sessions":5,"research":{"break_above_10close_high_pct":up,"break_below_10close_low_pct":dn},"paper_only":True,"live_order_placement":False}]
