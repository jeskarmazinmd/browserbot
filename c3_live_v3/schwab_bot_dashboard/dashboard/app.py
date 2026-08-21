from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

DATA_DIR = Path(os.environ.get("BOT_DATA_DIR", "/data"))
BOT_OUTPUT = DATA_DIR / "bot_output.txt"
DAILY_PNL = DATA_DIR / "daily_pnl_history.json"
DAILY_DEPLOYMENT = DATA_DIR / "daily_live_deployment_history.json"
ELIGIBILITY = DATA_DIR / "eligibility_status.json"
MARKET_TOKEN = DATA_DIR / "schwab_token.json"
TOKEN_LEASE_SECRET = os.environ.get("MARKET_TOKEN_LEASE_SECRET", "")

app = FastAPI(title="Schwab Bot Dashboard", docs_url="/docs")

security = HTTPBasic()

USERNAME = os.environ.get("DASHBOARD_USERNAME", "jay")
PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD")

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    if not (
        secrets.compare_digest(credentials.username, USERNAME)
        and secrets.compare_digest(credentials.password, PASSWORD)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Schwab Research Bot</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#0b1020; --panel:#131a2b; --panel2:#182136; --line:#293550;
      --text:#e8edf7; --muted:#98a6c2; --good:#45d483; --bad:#ff6b73;
      --warn:#f2c14e; --accent:#77a8ff;
    }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header { position:sticky; top:0; z-index:3; background:rgba(11,16,32,.94);
      backdrop-filter:blur(10px); border-bottom:1px solid var(--line); padding:18px 24px; }
    .top { display:flex; align-items:center; justify-content:space-between; gap:16px; max-width:1500px; margin:auto; }
    h1 { margin:0; font-size:20px; }
    .status { display:flex; align-items:center; gap:8px; color:var(--muted); font-size:13px; }
    .dot { width:10px; height:10px; border-radius:50%; background:var(--warn); }
    main { max-width:1500px; margin:auto; padding:22px; }
    .cards { display:grid; grid-template-columns:repeat(5,minmax(145px,1fr)); gap:12px; margin-bottom:16px; }
    .card,.panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; }
    .card { padding:15px; min-height:96px; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }
    .value { font-size:24px; font-weight:700; margin-top:10px; }
    .sub { color:var(--muted); font-size:12px; margin-top:5px; }
    .grid { display:grid; grid-template-columns:1.45fr 1fr; gap:16px; }
    .panel { padding:16px; overflow:hidden; }
    .panel h2 { font-size:15px; margin:0 0 13px; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th { text-align:left; color:var(--muted); font-weight:600; border-bottom:1px solid var(--line); padding:9px 8px; }
    td { border-bottom:1px solid rgba(41,53,80,.65); padding:9px 8px; white-space:nowrap; }
    tr:last-child td { border-bottom:0; }
    .positive { color:var(--good); } .negative { color:var(--bad); }
    .pill { display:inline-block; padding:3px 7px; border-radius:999px; background:var(--panel2); color:var(--muted); }
    pre { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; max-height:520px; overflow:auto;
      font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; color:#cbd5e7; }
    .toolbar { display:flex; gap:8px; align-items:center; margin-bottom:12px; }
    input { width:100%; background:var(--panel2); border:1px solid var(--line); color:var(--text);
      border-radius:8px; padding:9px 10px; }
    .footer { color:var(--muted); font-size:12px; margin-top:14px; }
    @media (max-width:1000px) { .cards{grid-template-columns:repeat(2,1fr)} .grid{grid-template-columns:1fr} }
    @media (max-width:560px) { .cards{grid-template-columns:1fr} main{padding:12px} header{padding:14px} }
  </style>
</head>
<body>
<header><div class="top">
  <h1>Schwab Research Bot</h1>
  <div class="status"><span class="dot" id="dot"></span><span id="status">Loading…</span></div>
</div></header>
<main>
  <h2 style="margin:0 0 12px;font-size:22px">Mission Control</h2>
  <section class="cards">
    <div class="card"><div class="label">Overall health</div><div class="value" id="botStatus">—</div><div class="sub" id="lastUpdate">—</div></div>
    <div class="card"><div class="label">Storage</div><div class="value" id="storage">—</div><div class="sub" id="storageSub">—</div></div>
    <div class="card"><div class="label">CPU</div><div class="value" id="cpu">—</div><div class="sub" id="cpuSub">—</div></div>
    <div class="card"><div class="label">Strategies</div><div class="value" id="strategyCount">—</div><div class="sub">with recorded paper trades</div></div>
    <div class="card"><div class="label">Research trades</div><div class="value" id="tradeCount">—</div><div class="sub">overlapping research variants</div></div>
  </section>

  <section class="grid">
    <div class="panel">
      <h2>Current paper P/L</h2>
      <div style="overflow:auto"><table>
        <thead><tr><th>Strategy</th><th>Total P/L</th><th>Closed</th><th>Open</th><th>Trades</th></tr></thead>
        <tbody id="pnlRows"></tbody>
      </table></div>
    </div>
    <div class="panel">
      <h2>System health</h2>
      <div style="overflow:auto"><table><tbody id="healthRows"></tbody></table></div>
    </div>
    <div class="panel">
      <h2>Daily P/L history</h2>
      <div style="overflow:auto"><table id="historyTable"></table></div>
    </div>
    <div class="panel">
      <div class="toolbar"><h2 style="margin:0;min-width:max-content">Raw bot output</h2><input id="search" placeholder="Filter output"></div>
      <pre id="raw">Loading…</pre>
    </div>
  </section>
  <div class="footer">Read-only dashboard. Refreshes every 10 seconds. It never places orders or edits strategy settings.</div>
</main>
<script>
const fmtMoney = n => n == null ? "—" : (n >= 0 ? "+" : "") + Number(n).toFixed(2);
const cls = n => Number(n) > 0 ? "positive" : Number(n) < 0 ? "negative" : "";
function setText(id, value){ document.getElementById(id).textContent = value ?? "—"; }
function renderHistory(history){
  const table=document.getElementById("historyTable");
  const days=Object.keys(history||{}).sort().slice(-7);
  if(!days.length){ table.innerHTML="<tbody><tr><td>No completed days saved yet.</td></tr></tbody>"; return; }
  const strategies=[...new Set(days.flatMap(d=>Object.keys(history[d]||{})))];
  table.innerHTML="<thead><tr><th>Strategy</th>"+days.map(d=>`<th>${d.slice(5)}</th>`).join("")+"</tr></thead><tbody>"+
    strategies.map(s=>"<tr><td>"+s+"</td>"+days.map(d=>{
      const v=(history[d]||{})[s]; return `<td class="${cls(v)}">${v==null?"—":fmtMoney(v)}</td>`;
    }).join("")+"</tr>").join("")+"</tbody>";
}
let latestRaw="";
async function refresh(){
  try{
    const r=await fetch("/api/dashboard",{cache:"no-store"}); const d=await r.json();
    latestRaw=d.raw_output||"";
    setText("botStatus",d.summary.status||"UNKNOWN");
    setText("lastUpdate",d.summary.last_update ? "Updated "+d.summary.last_update : "No update time");
    setText("storage",d.summary.storage_percent==null?"—":d.summary.storage_percent.toFixed(1)+"%");
    setText("storageSub",d.summary.storage_detail||"");
    setText("cpu",d.summary.cpu_percent==null?"—":d.summary.cpu_percent.toFixed(1)+"%");
    setText("cpuSub",d.summary.cpu_detail||"");
    setText("strategyCount",d.pnl.length);
    setText("tradeCount",d.pnl.reduce((a,x)=>a+(x.trades||0),0));
    document.getElementById("pnlRows").innerHTML=d.pnl.map(x=>`<tr>
      <td><span class="pill">${x.label}</span></td>
      <td class="${cls(x.total_pnl)}">${fmtMoney(x.total_pnl)}</td>
      <td>${x.closed}</td><td>${x.open_marked}</td><td>${x.trades}</td></tr>`).join("") ||
      "<tr><td colspan=5>No paper outcomes recorded today.</td></tr>";
    document.getElementById("healthRows").innerHTML=Object.entries(d.health).map(([k,v])=>
      `<tr><th>${k.replaceAll("_"," ")}</th><td>${v}</td></tr>`).join("");
    renderHistory(d.daily_pnl_history);
    applyFilter();
    setText("status",d.summary.stale?"Output is stale":"Dashboard connected");
    const dot=document.getElementById("dot");
    dot.style.background=d.summary.stale?"var(--warn)":"var(--good)";
  }catch(e){
    setText("status","Dashboard API unavailable");
    document.getElementById("dot").style.background="var(--bad)";
  }
}
function applyFilter(){
  const q=document.getElementById("search").value.toLowerCase();
  document.getElementById("raw").textContent=q ? latestRaw.split("\n").filter(x=>x.toLowerCase().includes(q)).join("\n") : latestRaw;
}
document.getElementById("search").addEventListener("input",applyFilter);
refresh(); setInterval(refresh,10000);
</script>
</body></html>"""

def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except Exception:
        return ""

def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def find_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.I)
    return float(match.group(1)) if match else None

def parse_summary(text: str) -> dict[str, Any]:
    status_match = re.search(r"^Status:\s*(.+)$", text, re.M | re.I)
    update_match = re.search(r"^Last update:\s*(.+)$", text, re.M | re.I)
    storage = find_float(r"data_use_percent:\s*([\d.]+)", text)
    cpu = find_float(r"(?:cpu_use_percent|cpu_percent|process_cpu_percent):\s*([\d.]+)", text)
    storage_line = re.search(r"data_used:\s*(.+)$", text, re.M | re.I)
    cpu_line = re.search(r"(?:cpu_detail|load_average|cpu_count):\s*(.+)$", text, re.M | re.I)

    stale = True
    raw_update = update_match.group(1).strip() if update_match else None
    if raw_update:
        try:
            dt = datetime.fromisoformat(raw_update.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            stale = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() > 180
        except Exception:
            pass

    return {
        "status": status_match.group(1).strip() if status_match else ("RUNNING" if text else "NO DATA"),
        "last_update": raw_update,
        "storage_percent": storage,
        "storage_detail": storage_line.group(1).strip() if storage_line else "",
        "cpu_percent": cpu,
        "cpu_detail": cpu_line.group(1).strip() if cpu_line else "",
        "stale": stale,
    }

def parse_health(text: str) -> dict[str, str]:
    wanted = {
        "quote_collection", "signal_generation", "order_placement",
        "access_status", "auth_status", "manual_reauth_due_utc",
        "data_available", "data_use_percent"
    }
    found: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key in wanted and key not in found:
            found[key] = value.strip()
    return found or {"status": "No structured health fields found"}

PNL_RE = re.compile(
    r"^(?P<label>[^:\n]+):\s*current_total_P/L=(?P<total>[+-]?[\d.]+)\s*\|\s*"
    r"closed=(?P<closed>\d+)\s*\((?P<closed_pnl>[+-]?[\d.]+)\)\s*\|\s*"
    r"open_marked=(?P<open>\d+)\s*\((?P<open_pnl>[+-]?[\d.]+)\)\s*\|\s*"
    r"open_unavailable=(?P<unavailable>\d+)\s*\|\s*trades=(?P<trades>\d+)",
    re.M
)

def parse_pnl(text: str) -> list[dict[str, Any]]:
    rows = []
    for m in PNL_RE.finditer(text):
        label = m.group("label").strip()
        if label.upper().startswith("ALL PAPER SERIES"):
            continue
        rows.append({
            "label": label,
            "total_pnl": float(m.group("total")),
            "closed": int(m.group("closed")),
            "closed_pnl": float(m.group("closed_pnl")),
            "open_marked": int(m.group("open")),
            "open_pnl": float(m.group("open_pnl")),
            "open_unavailable": int(m.group("unavailable")),
            "trades": int(m.group("trades")),
        })
    rows.sort(key=lambda x: x["total_pnl"], reverse=True)
    return rows

@app.get("/", response_class=HTMLResponse)
def index(user: str = Depends(authenticate)) -> str:
    return INDEX_HTML

@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "data_dir": str(DATA_DIR), "bot_output_exists": BOT_OUTPUT.exists()}

def _private_fly_client(request: Request) -> bool:
    """Allow only direct Fly private-network traffic, not the public proxy."""
    raw = request.headers.get("fly-client-ip")
    if not raw and request.client:
        raw = request.client.host
    if not raw:
        return False
    try:
        address = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return False
    return address.version == 6 and address in ipaddress.ip_network("fdaa::/16")


@app.get("/internal/market-access-token", include_in_schema=False)
def market_access_token(request: Request, response: Response) -> dict[str, Any]:
    if not _private_fly_client(request):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    supplied = request.headers.get("x-token-lease-secret", "")
    if not TOKEN_LEASE_SECRET or not secrets.compare_digest(supplied, TOKEN_LEASE_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    try:
        document = json.loads(MARKET_TOKEN.read_text())
        token = document["token"]
        access_token = str(token["access_token"])
        expires_at = float(token["expires_at"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market token unavailable",
        )
    if not access_token or expires_at <= datetime.now(timezone.utc).timestamp() + 10:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market access token expired",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"access_token": access_token, "expires_at": expires_at, "token_type": "Bearer"}


@app.get("/api/dashboard")
def dashboard(user: str = Depends(authenticate)) -> dict[str, Any]:
    raw = read_text(BOT_OUTPUT)
    usage = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else Path("/"))
    summary = parse_summary(raw)
    if summary["storage_percent"] is None:
        summary["storage_percent"] = usage.used / usage.total * 100
        summary["storage_detail"] = f"{usage.used/1024**2:.0f} MB / {usage.total/1024**2:.0f} MB"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "health": parse_health(raw),
        "pnl": parse_pnl(raw),
        "daily_pnl_history": read_json(DAILY_PNL),
        "daily_deployment_history": read_json(DAILY_DEPLOYMENT),
        "eligibility": read_json(ELIGIBILITY),
        "raw_output": raw[-500_000:],
    }
