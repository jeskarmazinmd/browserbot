"""STSECTOR1: fade dynamic stock residuals against their broad sector proxy."""
from collections import defaultdict,deque
from datetime import datetime,timezone
STRATEGY_ID="STSECTOR1";FAMILY="STATARB6";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
GROUPS={"XLK":("MSFT","AAPL","CRM","ORCL"),"SMH":("NVDA","AMD","AVGO","MU","INTC"),"XLF":("JPM","BAC","GS"),"XLY":("AMZN","TSLA"),"XLC":("GOOGL","META","NFLX")}
class Strategy:
 name=STRATEGY_ID
 def __init__(self):self.h=defaultdict(lambda:deque(maxlen=40));self.last=None
 def evaluate(self,snapshot):
  now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc);q=snapshot.get("quotes",{})
  for s,x in q.items():self.h[s].append((float(x["bid"])+float(x["ask"]))/2)
  if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1800):return []
  best=None
  for proxy,members in GROUPS.items():
   if proxy not in q or len(self.h[proxy])<21:continue
   pp=list(self.h[proxy]);pret=(pp[-1]/pp[-21]-1)*100
   for s in members:
    if s not in q or len(self.h[s])<21:continue
    p=list(self.h[s]);ret=(p[-1]/p[-21]-1)*100;res=ret-pret
    if abs(res)>=.8 and (best is None or abs(res)>abs(best[0])):best=(res,s,proxy,ret,pret)
  if not best:return []
  res,s,proxy,ret,pret=best;side="SHORT" if res>0 else "LONG";hedge="LONG" if res>0 else "SHORT";self.last=now
  return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":[{"symbol":s,"side":side,"bid":float(q[s]["bid"]),"ask":float(q[s]["ask"]),"weight":1},{"symbol":proxy,"side":hedge,"bid":float(q[proxy]["bid"]),"ask":float(q[proxy]["ask"]),"weight":1}],"target_pct":.55,"stop_pct":.45,"max_hold_minutes":120,"research":{"sector_proxy":proxy,"stock_return_20m_pct":ret,"proxy_return_20m_pct":pret,"residual_pct":res},"paper_only":True,"live_order_placement":False}]
