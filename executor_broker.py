from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path


TOKEN_PATH = Path(os.environ.get("EXECUTOR_TOKEN_PATH", "/data/schwab_executor_token.json"))


def response_value(response):
    try:
        body = response.json()
    except Exception:
        body = response.text
    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": body,
    }


class Broker:
    def __init__(self):
        from schwab.auth import client_from_token_file

        key = os.environ.get("SCHWAB_TRADING_APP_KEY")
        secret = os.environ.get("SCHWAB_TRADING_SECRET")
        if not key or not secret:
            raise RuntimeError("executor trading app key/secret missing")
        if not TOKEN_PATH.exists():
            raise RuntimeError(f"executor token missing: {TOKEN_PATH}")
        self.client = client_from_token_file(str(TOKEN_PATH), key, secret)
        self.account_hash, self.account_number = self._resolve_account()

    def _resolve_account(self):
        result = response_value(self.client.get_account_numbers())
        if not result["ok"] or not isinstance(result["body"], list):
            raise RuntimeError(f"account lookup failed: {result}")
        accounts = [row for row in result["body"] if row.get("hashValue")]
        requested = os.environ.get("EXECUTOR_ACCOUNT_NUMBER", "").strip()
        if requested:
            accounts = [row for row in accounts if str(row.get("accountNumber")) == requested]
        if len(accounts) != 1:
            raise RuntimeError(
                "executor requires exactly one resolved account; set "
                "EXECUTOR_ACCOUNT_NUMBER when multiple accounts are linked"
            )
        return str(accounts[0]["hashValue"]), str(accounts[0].get("accountNumber") or "")

    def positions(self):
        from schwab.client import Client

        response = self.client.get_account(
            self.account_hash,
            fields=[Client.Account.Fields.POSITIONS],
        )
        result = response_value(response)
        account = result["body"].get("securitiesAccount", {}) if isinstance(result["body"], dict) else {}
        result["positions"] = account.get("positions", []) or []
        result["balances"] = account.get("currentBalances", {}) or {}
        return result

    def recent_orders(self, minutes=30):
        now = datetime.now(timezone.utc)
        response = self.client.get_orders_for_account(
            self.account_hash,
            max_results=100,
            from_entered_datetime=now - timedelta(minutes=minutes),
            to_entered_datetime=now,
        )
        result = response_value(response)
        result["orders"] = result["body"] if isinstance(result["body"], list) else []
        return result

    def place_limit(self, symbol, side, price):
        from schwab.orders.equities import equity_buy_limit, equity_sell_limit

        builder = equity_buy_limit if side == "BUY" else equity_sell_limit
        order = builder(symbol, 1, float(price)).build()
        return response_value(self.client.place_order(self.account_hash, order))

    def cancel(self, order_id):
        return response_value(self.client.cancel_order(int(order_id), self.account_hash))


def position_quantity(positions, symbol):
    quantity = 0.0
    for position in positions:
        instrument = position.get("instrument", {}) or {}
        if str(instrument.get("symbol", "")).upper() != symbol.upper():
            continue
        quantity += float(position.get("longQuantity", 0) or 0)
        quantity -= float(position.get("shortQuantity", 0) or 0)
    return quantity


def active_orders(orders):
    active = {
        "AWAITING_PARENT_ORDER", "AWAITING_CONDITION", "ACCEPTED", "QUEUED",
        "WORKING", "PENDING_ACTIVATION", "PENDING_CANCEL", "PARTIALLY_FILLED",
    }
    return [row for row in orders if str(row.get("status", "")).upper() in active]
