#!/bin/bash
set -e

cd "$HOME/Desktop/browserbot" || exit 1
source venv/bin/activate

APP_KEY=$(grep '^SCHWAB_APP_KEY=' schwabkey.txt | cut -d= -f2-)
APP_SECRET=$(grep '^SCHWAB_SECRET=' schwabkey.txt | cut -d= -f2-)

echo "Refreshing Schwab token..."

python3 scannerenv/bin/schwab-generate-token.py \
  --token_file schwab_token.json \
  --api_key "$APP_KEY" \
  --app_secret "$APP_SECRET" \
  --callback_url "https://127.0.0.1:8182"

echo "Uploading token directly to Fly /data..."
printf 'put schwab_token.json /data/schwab_token_new.json\n' | fly sftp shell -a schwab
fly ssh console -a schwab -C 'mv /data/schwab_token_new.json /data/schwab_token.json'

echo "Restarting Fly app..."
fly apps restart schwab

echo "Waiting for Fly SSH to come back..."
sleep 15

echo "Checking bot output..."
fly ssh console -a schwab -C 'cat /data/bot_output.txt'

echo
echo "Done. You can close this window."
read -n 1 -s -r -p "Press any key to close..."
