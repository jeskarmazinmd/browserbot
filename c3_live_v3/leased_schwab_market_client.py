"""Read-only Schwab market client backed by the research bot's private token lease."""
import requests

class LeasedSchwabMarketClient:
    def __init__(self, lease_url, lease_secret, timeout=20):
        if not lease_url:
            raise ValueError("MARKET_TOKEN_LEASE_URL is required")
        if not lease_secret:
            raise ValueError("TOKEN_LEASE_SECRET is required")
        self.lease_url = lease_url
        self.lease_secret = lease_secret
        self.timeout = timeout

    def _access_token(self):
        r = requests.get(
            self.lease_url,
            headers={"x-token-lease-secret": self.lease_secret},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def get_quotes(self, symbols, *, fields=None, indicative=False):
        token = self._access_token()
        params = {"symbols": ",".join(symbols)}
        if fields:
            if isinstance(fields, (list, tuple, set)):
                params["fields"] = ",".join(str(x) for x in fields)
            else:
                params["fields"] = str(fields)
        if indicative:
            params["indicative"] = "true"
        return requests.get(
            "https://api.schwabapi.com/marketdata/v1/quotes",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout,
        )
