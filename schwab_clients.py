import requests
from datetime import datetime, timedelta, timezone
import time

class SchwabDataClient:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.schwabapi.com"

    def get_quotes(self):
        # placeholder if you later expand direct API usage
        return {}


class SchwabTradeClient:
    def __init__(self, token, account_id, sdk_client=None):
        self.token = token
        self.account_id = account_id
        self.sdk_client = sdk_client
        self.base = "https://api.schwabapi.com"
        self.enabled = False  # Real order placement is explicitly armed.


    def _post_order(self, payload):
        if not self.enabled:
            return {
                "ok": False,
                "status": "SAFE_MODE_BLOCKED",
                "payload": payload,
            }

        url = f"{self.base}/trader/v1/accounts/{self.account_id}/orders"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        try:
            r = requests.post(url, json=payload, headers=headers)
            try:
                body = r.json()
            except Exception:
                body = r.text

            return {
                "ok": 200 <= r.status_code < 300,
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": body,
                "payload": payload,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "payload": payload,
            }

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, url, params=None):
        try:
            r = requests.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=20,
            )
            try:
                body = r.json()
            except Exception:
                body = r.text

            return {
                "ok": 200 <= r.status_code < 300,
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": body,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

    def _delete(self, url):
        try:
            r = requests.delete(
                url,
                headers=self._headers(),
                timeout=20,
            )
            try:
                body = r.json()
            except Exception:
                body = r.text

            return {
                "ok": 200 <= r.status_code < 300,
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": body,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

    @staticmethod
    def _order_id_from_response(response):
        headers = response.get("headers", {}) or {}
        location = headers.get("Location") or headers.get("location")

        if not location:
            return None

        return str(location).rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _normalize_sdk_response(response):
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

    def get_account_positions(self):
        if self.sdk_client is None:
            return {
                "ok": False,
                "error": "schwab-py SDK client unavailable",
            }

        try:
            from schwab.client import Client

            response = self.sdk_client.get_account(
                self.account_id,
                fields=[Client.Account.Fields.POSITIONS],
            )
            result = self._normalize_sdk_response(response)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

        if not result.get("ok"):
            return result

        body = result.get("body")
        if not isinstance(body, dict):
            return {
                **result,
                "ok": False,
                "error": "Unexpected account response format",
            }

        account = body.get("securitiesAccount", body)
        result["positions"] = account.get("positions", []) or []
        return result

    def get_net_position_qty(self, symbol):
        result = self.get_account_positions()

        if not result.get("ok"):
            return {
                **result,
                "quantity": None,
            }

        symbol = str(symbol).upper()
        qty = 0.0

        for position in result.get("positions", []):
            instrument = position.get("instrument", {}) or {}

            if str(instrument.get("symbol", "")).upper() != symbol:
                continue

            qty += float(position.get("longQuantity", 0) or 0)
            qty -= float(position.get("shortQuantity", 0) or 0)

        return {
            **result,
            "quantity": qty,
        }

    def get_order(self, order_id):
        if self.sdk_client is None:
            return {
                "ok": False,
                "error": "schwab-py SDK client unavailable",
            }

        try:
            response = self.sdk_client.get_order(
                int(order_id),
                self.account_id,
            )
            return self._normalize_sdk_response(response)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

    def get_recent_orders(self, lookback_days=2):
        if self.sdk_client is None:
            return {
                "ok": False,
                "error": "schwab-py SDK client unavailable",
            }

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)

        try:
            response = self.sdk_client.get_orders_for_account(
                self.account_id,
                max_results=500,
                from_entered_datetime=start,
                to_entered_datetime=now,
            )
            result = self._normalize_sdk_response(response)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

        if not result.get("ok"):
            return result

        body = result.get("body")
        result["orders"] = body if isinstance(body, list) else []
        return result

    def cancel_order(self, order_id):
        if self.sdk_client is None:
            return {
                "ok": False,
                "error": "schwab-py SDK client unavailable",
            }

        try:
            response = self.sdk_client.cancel_order(
                int(order_id),
                self.account_id,
            )
            return self._normalize_sdk_response(response)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "exception_type": type(e).__name__,
            }

    @staticmethod
    def _walk_orders(order):
        if not isinstance(order, dict):
            return

        yield order

        for child in order.get("childOrderStrategies", []) or []:
            yield from SchwabTradeClient._walk_orders(child)

    @staticmethod
    def _walk_orders_with_ancestors(order, ancestors=None):
        """Yield every order node together with its ancestor order nodes."""
        if not isinstance(order, dict):
            return

        ancestors = list(ancestors or [])
        yield order, ancestors

        next_ancestors = ancestors + [order]

        for child in order.get("childOrderStrategies", []) or []:
            yield from SchwabTradeClient._walk_orders_with_ancestors(
                child,
                next_ancestors,
            )

    @staticmethod
    def _order_has_symbol_side(order, symbol, instruction):
        symbol = str(symbol).upper()
        instruction = str(instruction).upper()

        for leg in order.get("orderLegCollection", []) or []:
            instrument = leg.get("instrument", {}) or {}

            leg_symbol = str(
                instrument.get("symbol", "")
            ).upper()

            leg_instruction = str(
                leg.get("instruction", "")
            ).upper()

            if (
                leg_symbol == symbol
                and leg_instruction == instruction
            ):
                return True

        return False


    @staticmethod
    def extract_fill_summary(order, recursive=True):
        """Return quantity-weighted execution price/time from an order or tree."""
        executions = []
        nodes = SchwabTradeClient._walk_orders(order) if recursive else [order]
        for node in nodes:
            for activity in node.get("orderActivityCollection", []) or []:
                for leg in activity.get("executionLegs", []) or []:
                    try:
                        qty = float(leg.get("quantity", 0) or 0)
                        price = float(leg.get("price", 0) or 0)
                    except Exception:
                        continue
                    if qty <= 0 or price <= 0:
                        continue
                    executions.append({
                        "quantity": qty,
                        "price": price,
                        "time": leg.get("time") or activity.get("executionTime"),
                    })

        total_qty = sum(x["quantity"] for x in executions)
        if total_qty <= 0:
            return {"filled_quantity": 0.0, "average_price": None, "fill_time": None, "executions": []}

        average_price = sum(x["quantity"] * x["price"] for x in executions) / total_qty
        fill_times = [x["time"] for x in executions if x.get("time")]
        return {
            "filled_quantity": total_qty,
            "average_price": average_price,
            "fill_time": max(fill_times) if fill_times else None,
            "executions": executions,
        }

    def get_order_fill_summary(self, order_id):
        result = self.get_order(order_id)
        if not result.get("ok"):
            return result
        body = result.get("body") or {}
        # The parent TRIGGER node contains the BUY fill. Do not mix later
        # child OCO sell executions into the entry average.
        return {**result, **self.extract_fill_summary(body, recursive=False)}

    def find_latest_filled_sell(self, symbol, entered_after=None):
        """Find the most recent filled SELL execution for a symbol."""
        result = self.get_recent_orders(lookback_days=3)
        if not result.get("ok"):
            return result

        matches = []
        for root in result.get("orders", []):
            for node in self._walk_orders(root):
                if not self._order_has_symbol_side(node, symbol, "SELL"):
                    continue
                status = str(node.get("status", "")).upper()
                summary = self.extract_fill_summary(node, recursive=False)
                if status != "FILLED" and summary.get("filled_quantity", 0) <= 0:
                    continue
                entered = node.get("enteredTime") or root.get("enteredTime")
                fill_time = summary.get("fill_time") or node.get("closeTime") or entered
                if entered_after and fill_time and str(fill_time) < str(entered_after):
                    continue
                matches.append({
                    "order_id": str(node.get("orderId") or root.get("orderId") or ""),
                    "status": status,
                    "order_type": node.get("orderType"),
                    "average_price": summary.get("average_price"),
                    "filled_quantity": summary.get("filled_quantity"),
                    "fill_time": fill_time,
                    "entered_time": entered,
                })

        matches.sort(key=lambda x: str(x.get("fill_time") or x.get("entered_time") or ""), reverse=True)
        return {**result, "match": matches[0] if matches else None, "matches": matches}

    def find_active_exit_orders(self, symbol):
        """Find active nested SELL orders, regardless of root-order status."""
        active_statuses = {
            "AWAITING_PARENT_ORDER",
            "AWAITING_CONDITION",
            "AWAITING_STOP_CONDITION",
            "AWAITING_MANUAL_REVIEW",
            "ACCEPTED",
            "AWAITING_UR_OUT",
            "PENDING_ACTIVATION",
            "QUEUED",
            "WORKING",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
            "PARTIALLY_FILLED",
        }

        result = self.get_recent_orders()

        if not result.get("ok"):
            return result

        matches = []
        seen = set()

        for root in result.get("orders", []):
            for node, ancestors in self._walk_orders_with_ancestors(root):
                status = str(node.get("status", "")).upper()
                order_id = node.get("orderId")

                if status not in active_statuses:
                    continue

                if not order_id:
                    continue

                if not self._order_has_symbol_side(
                    node,
                    symbol,
                    "SELL",
                ):
                    continue

                order_id = str(order_id)

                if order_id in seen:
                    continue

                seen.add(order_id)

                ancestor_ids = []

                # Nearest ancestor first, then outward toward the root.
                for ancestor in reversed(ancestors):
                    ancestor_id = ancestor.get("orderId")

                    if ancestor_id:
                        ancestor_ids.append(str(ancestor_id))

                matches.append({
                    "order_id": order_id,
                    "status": status,
                    "order_type": node.get("orderType"),
                    "strategy_type": node.get("orderStrategyType"),
                    "ancestor_order_ids": ancestor_ids,
                })

        return {
            **result,
            "orders": matches,
        }

    def cancel_active_exit_orders(self, symbol):
        """Cancel active SELL exits and confirm that none remain.

        Child order IDs are tried first. Ancestor IDs are fallback cancellation
        candidates because Schwab may require cancellation at the containing
        OCO or trigger level for some nested-order states.
        """
        found = self.find_active_exit_orders(symbol)

        if not found.get("ok"):
            return found

        active_orders = found.get("orders", [])

        if not active_orders:
            return {
                "ok": True,
                "attempts": [],
                "remaining": [],
                "note": "No active sell exits found",
            }

        candidate_ids = []

        for order in active_orders:
            candidate_ids.append(order["order_id"])
            candidate_ids.extend(order.get("ancestor_order_ids", []))

        # Preserve order while removing duplicates.
        candidate_ids = list(dict.fromkeys(candidate_ids))

        attempts = []

        for order_id in candidate_ids:
            response = self.cancel_order(order_id)

            attempts.append({
                "order_id": order_id,
                "response": response,
            })

            # Re-query after every successful cancellation. Cancelling one OCO
            # level may remove both exit children.
            if response.get("ok"):
                time.sleep(0.5)

                remaining_check = self.find_active_exit_orders(symbol)

                if (
                    remaining_check.get("ok")
                    and not remaining_check.get("orders")
                ):
                    return {
                        "ok": True,
                        "attempts": attempts,
                        "remaining": [],
                        "remaining_response": remaining_check,
                    }

        time.sleep(1)

        remaining = self.find_active_exit_orders(symbol)

        return {
            "ok": (
                remaining.get("ok") is True
                and not remaining.get("orders")
            ),
            "attempts": attempts,
            "remaining": remaining.get("orders", []),
            "remaining_response": remaining,
        }

    def place_entry_trigger_oco_order(self, symbol, qty, buy_limit_price, target_price, stop_price):
        payload = {
            "orderStrategyType": "TRIGGER",
            "session": "NORMAL",
            "duration": "DAY",
            "orderType": "LIMIT",
            "price": f"{buy_limit_price:.2f}",
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }],
            "childOrderStrategies": [{
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "LIMIT",
                        "price": f"{target_price:.2f}",
                        "orderLegCollection": [{
                            "instruction": "SELL",
                            "quantity": qty,
                            "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                        }]
                    },
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "STOP",
                        "stopPrice": f"{stop_price:.2f}",
                        "orderLegCollection": [{
                            "instruction": "SELL",
                            "quantity": qty,
                            "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                        }]
                    }
                ]
            }]
        }
        result = self._post_order(payload)
        result["order_id"] = self._order_id_from_response(result)
        return result

    def place_eod_sell_order(self, symbol, qty=1):
        payload = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "SELL",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }]
        }
        result = self._post_order(payload)
        result["order_id"] = self._order_id_from_response(result)
        return result

    def place_order(self, symbol, qty=1):
        if not self.enabled:
            return {"status": "SAFE_MODE_BLOCKED"}

        url = f"{self.base}/trader/v1/accounts/{self.account_id}/orders"

        payload = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": qty,
                "instrument": {
                    "symbol": symbol,
                    "assetType": "EQUITY"
                }
            }]
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        try:
            r = requests.post(url, json=payload, headers=headers)
            return r.json()
        except Exception as e:
            return {"error": str(e)}


def _place_sell_order(self, symbol, qty=1):
    if not self.enabled:
        return {"status": "SAFE_MODE_BLOCKED"}

    url = f"{self.base}/trader/v1/accounts/{self.account_id}/orders"

    payload = {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [{
            "instruction": "SELL",
            "quantity": qty,
            "instrument": {
                "symbol": symbol,
                "assetType": "EQUITY"
            }
        }]
    }

    headers = {
        "Authorization": f"Bearer {self.token}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

SchwabTradeClient.place_sell_order = _place_sell_order
