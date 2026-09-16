from __future__ import annotations

import os
from pathlib import Path

from schwab.auth import client_from_manual_flow

from executor_broker import TOKEN_PATH


def main():
    key = os.environ.get("SCHWAB_TRADING_APP_KEY")
    secret = os.environ.get("SCHWAB_TRADING_SECRET")
    callback = os.environ.get("SCHWAB_TRADING_CALLBACK_URL")
    if not key or not secret or not callback:
        raise SystemExit(
            "SCHWAB_TRADING_APP_KEY, SCHWAB_TRADING_SECRET, and "
            "SCHWAB_TRADING_CALLBACK_URL are required"
        )
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    client_from_manual_flow(key, secret, callback, str(TOKEN_PATH))
    os.chmod(TOKEN_PATH, 0o600)
    print(f"executor token created: {TOKEN_PATH}")


if __name__ == "__main__":
    main()
