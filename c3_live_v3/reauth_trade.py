import os
from schwab.auth import client_from_manual_flow

client_from_manual_flow(
    api_key=os.environ["SCHWAB_TRADING_APP_KEY"],
    app_secret=os.environ["SCHWAB_TRADING_SECRET"],
    callback_url="https://127.0.0.1:8183",
    token_path="/data/schwab_trade_token.json",
)

print("trade token saved to /data/schwab_trade_token.json")
