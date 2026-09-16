#!/usr/bin/env python3
"""Install private market-access-token leasing for the dedicated C3 validator."""
from __future__ import annotations

import py_compile
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1))


dashboard = Path("schwab_bot_dashboard/dashboard/app.py")
c3 = Path("c3_live_service.py")
fly = Path("fly.c3live.toml")

replace_once(dashboard, "import json\n", "import ipaddress\nimport json\n")
replace_once(
    dashboard,
    "from fastapi import FastAPI, Depends, HTTPException, status\n",
    "from fastapi import FastAPI, Depends, HTTPException, Request, Response, status\n",
)
replace_once(
    dashboard,
    'ELIGIBILITY = DATA_DIR / "eligibility_status.json"\n',
    'ELIGIBILITY = DATA_DIR / "eligibility_status.json"\n'
    'MARKET_TOKEN = DATA_DIR / "schwab_token.json"\n'
    'TOKEN_LEASE_SECRET = os.environ.get("MARKET_TOKEN_LEASE_SECRET", "")\n',
)

lease_route = '''def _private_fly_client(request: Request) -> bool:
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


'''
replace_once(
    dashboard,
    '@app.get("/api/dashboard")\ndef dashboard(user: str = Depends(authenticate)) -> dict[str, Any]:\n',
    lease_route + '@app.get("/api/dashboard")\ndef dashboard(user: str = Depends(authenticate)) -> dict[str, Any]:\n',
)

replace_once(c3, "import pandas as pd\n", "import pandas as pd\nimport requests\n")
replace_once(
    c3,
    "    fetch_schwab_quote_snapshots, get_schwab_client, load_symbols,\n",
    "    fetch_schwab_quote_snapshots, load_symbols,\n",
)
replace_once(
    c3,
    'SLOT_NOTIONAL = float(os.getenv("C3_SLOT_NOTIONAL", "1000"))\n',
    'SLOT_NOTIONAL = float(os.getenv("C3_SLOT_NOTIONAL", "1000"))\n'
    'TOKEN_LEASE_URL = os.getenv(\n'
    '    "MARKET_TOKEN_LEASE_URL",\n'
    '    "http://schwab.internal:8080/internal/market-access-token",\n'
    ')\n'
    'TOKEN_LEASE_SECRET = os.getenv("MARKET_TOKEN_LEASE_SECRET", "")\n'
    'SCHWAB_QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"\n',
)

client_class = '''

class LeasedMarketDataClient:
    """Quote client holding only a short-lived access token in memory."""

    def __init__(self):
        if not TOKEN_LEASE_SECRET:
            raise RuntimeError("MARKET_TOKEN_LEASE_SECRET is required")
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._access_token = ""
        self._expires_at = 0.0

    def _lease(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._access_token and self._expires_at > time.time() + 30:
                return self._access_token
            response = self._session.get(
                TOKEN_LEASE_URL,
                headers={"X-Token-Lease-Secret": TOKEN_LEASE_SECRET},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            self._access_token = str(payload["access_token"])
            self._expires_at = float(payload["expires_at"])
            counters["token_leases"] += 1
            return self._access_token

    def _request_quotes(self, symbols, token):
        return self._session.get(
            SCHWAB_QUOTES_URL,
            params={"symbols": ",".join(symbols)},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )

    def get_quotes(self, symbols):
        response = self._request_quotes(symbols, self._lease())
        if response.status_code == 401:
            response = self._request_quotes(symbols, self._lease(force=True))
        return response
'''
replace_once(
    c3,
    'metrics = {"universe_fetch_seconds": None, "priority_fetch_seconds": None}\n',
    'metrics = {"universe_fetch_seconds": None, "priority_fetch_seconds": None}\n' + client_class,
)

old_main = '''    ROOT.mkdir(parents=True, exist_ok=True)
    token_path = ROOT / "schwab_token.json"
    while not token_path.exists():
        atomic_json(STATUS, {
            "updated_at": datetime.now(timezone.utc),
            "strategy_id": strategy.STRATEGY_ID,
            "mode": "WAITING_FOR_MARKET_TOKEN",
            "live_order_placement_enabled": False,
        })
        time.sleep(10)
    symbols = [s for s in load_symbols() if s not in {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}]
    client = get_schwab_client()
'''
new_main = '''    ROOT.mkdir(parents=True, exist_ok=True)
    client = None
    while client is None:
        atomic_json(STATUS, {
            "updated_at": datetime.now(timezone.utc),
            "strategy_id": strategy.STRATEGY_ID,
            "mode": "WAITING_FOR_MARKET_TOKEN_LEASE",
            "live_order_placement_enabled": False,
        })
        try:
            client = LeasedMarketDataClient()
            client._lease()
        except Exception as exc:
            client = None
            emit("TOKEN_LEASE_WAIT", error=repr(exc))
            time.sleep(10)
    symbols = [s for s in load_symbols() if s not in {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}]
'''
replace_once(c3, old_main, new_main)

replace_once(
    fly,
    '  LIVE_ORDER_PLACEMENT_ENABLED = "0"\n',
    '  LIVE_ORDER_PLACEMENT_ENABLED = "0"\n'
    '  MARKET_TOKEN_LEASE_URL = "http://schwab.internal:8080/internal/market-access-token"\n',
)

py_compile.compile(str(dashboard), doraise=True)
py_compile.compile(str(c3), doraise=True)
print("Installed and compiled private market-token leasing successfully.")
