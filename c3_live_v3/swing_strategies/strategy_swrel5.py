"""SWREL5: five-session relative winners/losers versus SPY."""
from datetime import datetime,timezone
STRATEGY_ID="SWREL5";FAMILY="SWING6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.last_day=None
 def evaluate(self,s):
  now=s["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);hist=s.get("completed_daily_history",{});quotes=s.get("quotes",{});spy=hist.get("SPY",[])
  if now<datetime.fromisoformat(FORWARD_START_UTC) or self.last_day==now.date() or len(spy)<6:return []
  sr=(float(spy[-1][1])/float(spy[-6][1])-1)*100;rows=[]
  for sym,h in hist.items():
   q=quotes.get(sym)
   if sym=="SPY" or not q or len(h)<6:continue
   r=(float(h[-1][1])/float(h[-6][1])-1)*100;rows.append((r-sr,r,sym,q))
  if not rows:return []
  rows.sort();lo,hi=rows[0],rows[-1];out=[]
  if hi[0]>=3:out.append((hi,"LONG"))
  if lo[0]<=-3:out.append((lo,"SHORT"))
  if not out:return []
  self.last_day=now.date();return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":sym,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":4,"stop_pct":2.5,"max_hold_sessions":5,"research":{"relative_vs_spy_5session_pct":rel,"own_5session_return_pct":r,"spy_5session_return_pct":sr},"paper_only":True,"live_order_placement":False} for (rel,r,sym,q),side in out]
