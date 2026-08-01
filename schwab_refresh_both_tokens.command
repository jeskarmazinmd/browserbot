#!/bin/bash
set -e

cd "$HOME/Desktop/browserbot" || exit 1
source venv/bin/activate

echo "=== Refreshing Schwab MARKET DATA token ==="
MARKET_KEY=$(grep '^SCHWAB_APP_KEY=' schwabkey.txt | cut -d= -f2-)
MARKET_SECRET=$(grep '^SCHWAB_SECRET=' schwabkey.txt | cut -d= -f2-)

python3 scannerenv/bin/schwab-generate-token.py \
  --token_file schwab_token.json \
  --api_key "$MARKET_KEY" \
  --app_secret "$MARKET_SECRET" \
  --callback_url "https://127.0.0.1:8182"

echo "=== Uploading MARKET DATA token to Fly ==="
fly ssh sftp shell -a schwab <<'SFTP'
put schwab_token.json /data/schwab_token_new.json
exit
SFTP

fly ssh console -a schwab -C 'mv /data/schwab_token_new.json /data/schwab_token.json'

echo "=== Refreshing Schwab TRADING token ==="
TRADE_KEY=$(grep '^SCHWAB_TRADE_APP_KEY=' schwabtradekey.txt | cut -d= -f2-)
TRADE_SECRET=$(grep '^SCHWAB_TRADE_SECRET=' schwabtradekey.txt | cut -d= -f2-)

python3 scannerenv/bin/schwab-generate-token.py \
  --token_file schwab_trade_token.json \
  --api_key "$TRADE_KEY" \
  --app_secret "$TRADE_SECRET" \
  --callback_url "https://127.0.0.1:8183"

echo "=== Uploading TRADING token to Fly ==="
fly ssh sftp shell -a schwab <<'SFTP'
put schwab_trade_token.json /data/schwab_trade_token_new.json
exit
SFTP

fly ssh console -a schwab -C 'mv /data/schwab_trade_token_new.json /data/schwab_trade_token.json'

echo "=== Restarting Fly app ==="
fly apps restart schwab

echo "=== Waiting for Fly ==="
sleep 15

echo "=== Checking token timestamps ==="
fly ssh console -a schwab -C 'python3 -c '"'"'import json,datetime; 
for path,label in [("/data/schwab_token.json","market"),("/data/schwab_trade_token.json","trade")]:
    d=json.load(open(path))
    print(label+"_created_utc:", datetime.datetime.fromtimestamp(d["creation_timestamp"], datetime.timezone.utc).isoformat())
'"'"''

echo "=== Checking bot output ==="
fly ssh console -a schwab -C 'cat /data/bot_output.txt'

echo
echo "Done. You can close this window."
read -n 1 -s -r -p "Press any key to close..."
