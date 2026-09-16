from __future__ import annotations

import argparse
import json

from executor_broker import Broker, active_orders


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cancel-order-id")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    broker = Broker()
    if args.cancel_order_id:
        phrase = f"CANCEL ORDER {args.cancel_order_id}"
        if args.confirm != phrase:
            raise SystemExit(f"confirmation must exactly equal: {phrase}")
        print(json.dumps(broker.cancel(args.cancel_order_id), indent=2, default=str))
        return
    positions = broker.positions()
    orders = broker.recent_orders(minutes=7 * 24 * 60)
    print(json.dumps({
        "account_last4": broker.account_number[-4:],
        "positions_ok": positions.get("ok"),
        "positions": positions.get("positions", []),
        "orders_ok": orders.get("ok"),
        "active_orders": active_orders(orders.get("orders", [])),
        "recent_orders": orders.get("orders", [])[:10],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
