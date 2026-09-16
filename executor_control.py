from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import secrets


REQUEST = Path("/data/manual_test1_request.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=("BUY", "SELL"), required=True)
    parser.add_argument("--limit", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()
    allowed = {
        item.strip().upper()
        for item in os.environ.get("EXECUTOR_ALLOWED_SYMBOLS", "").split(",")
        if item.strip()
    }
    if symbol not in allowed:
        raise SystemExit("symbol is not allowlisted")
    try:
        price = Decimal(args.limit).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise SystemExit("invalid limit price") from exc
    maximum = Decimal(os.environ.get("EXECUTOR_MAX_NOTIONAL", "25"))
    if price <= 0 or price > maximum:
        raise SystemExit(f"limit must be between 0.01 and {maximum}")
    phrase = f"ARM ONE SHARE {args.side} {symbol} AT {price}"
    if args.confirm != phrase:
        raise SystemExit(f"confirmation must exactly equal: {phrase}")
    now = datetime.now(timezone.utc)
    value = {
        "intent_id": "manual-test1-" + secrets.token_hex(12),
        "strategy_id": "MANUAL_TEST1",
        "symbol": symbol,
        "side": args.side,
        "quantity": 1,
        "limit_price": str(price),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=45)).isoformat(),
    }
    temporary = REQUEST.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(REQUEST)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
