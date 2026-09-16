# Verified proactive Schwab market-token refresh

This amendment gives both Schwab token paths the same proof standard. Market and trading refresh below 20 minutes remaining, atomically persist the response, require at least 25 minutes on the reread token, and write bounded token-free evidence to `/data/auth_events.jsonl`. Market verifies a VOO quote; trading rebuilds the trader and requires successful account enablement.

No secrets or token values are logged. The existing weekly manual OAuth schedule remains necessary because access-token refresh does not extend an expired/revoked multi-day refresh token indefinitely.
