import os
from schwab.auth import client_from_manual_flow

client_from_manual_flow(
    api_key=os.environ["SCHWAB_MARKET_APP_KEY"],
    app_secret=os.environ["SCHWAB_MARKET_SECRET"],
    callback_url="https://127.0.0.1:8182",
    token_path="/data/schwab_token.json",
)

print("market token saved to /data/schwab_token.json")
