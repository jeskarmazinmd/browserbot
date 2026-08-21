# Schwab Bot Dashboard

A read-only web dashboard for the existing Fly.io bot.

## Why this design

The dashboard is a separate process. It reads the bot's files in `/data` and does not
import `live_strategy_runner.py`, call Schwab, place orders, or change strategies.

It currently reads:

- `/data/bot_output.txt`
- `/data/daily_pnl_history.json`
- `/data/daily_live_deployment_history.json`
- `/data/eligibility_status.json`

The page refreshes every 10 seconds.

## Local test

From your bot project directory:

```bash
python3 -m venv dashboard-venv
source dashboard-venv/bin/activate
pip install -r schwab_bot_dashboard/requirements-dashboard.txt

BOT_DATA_DIR=/path/to/a/local/data/folder \
uvicorn schwab_bot_dashboard.dashboard.app:app --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080
```

For a local visual test without real data, create a folder and copy a recent
`bot_output.txt` plus `daily_pnl_history.json` into it.

## Add it to the existing Docker image

Add these lines to the bot's Dockerfile:

```dockerfile
COPY schwab_bot_dashboard/requirements-dashboard.txt /tmp/requirements-dashboard.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dashboard.txt
COPY schwab_bot_dashboard /app/schwab_bot_dashboard
```

## Start it on Fly.io

The least disruptive first deployment is to add the dashboard as another child
under the existing supervisor. Start this command alongside the collector,
strategy runner, and leaderboard writer:

```bash
python -m uvicorn schwab_bot_dashboard.dashboard.app:app \
  --host 0.0.0.0 --port 8080
```

Your Fly service must point its internal port to `8080`.

Example `fly.toml` service block:

```toml
[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1
  processes = ["app"]
```

## Important deployment note

Do not replace the stable supervisor blindly. First add the dashboard child,
deploy, and confirm all four processes remain alive. The dashboard uses little CPU,
but its process should still be restarted by the supervisor if it exits.

## Endpoints

- `/` dashboard
- `/healthz` simple health check
- `/api/dashboard` parsed JSON
- `/docs` FastAPI API docs
