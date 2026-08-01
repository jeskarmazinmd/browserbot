from schwab.auth import easy_client

API_KEY = "PASTE_KEY_HERE"
APP_SECRET = "PASTE_SECRET_HERE"
CALLBACK_URL = "PASTE_CALLBACK_HERE"

easy_client(
    api_key=API_KEY,
    app_secret=APP_SECRET,
    callback_url=CALLBACK_URL,
    token_path="schwab_token.json",
)
print("token written to schwab_token.json")
