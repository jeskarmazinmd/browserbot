# C3 live runtime monitoring

The `schwab-c3-live` deployment is self-describing. Never infer the active
engine from historical filenames.

## Authoritative check

```bash
fly ssh console -a schwab-c3-live -C "python /app/check_c3_runtime.py"
```

The checker reads `/data/runtime_manifest.json`, follows only the canonical
paths declared there, verifies a current PID-bound heartbeat, and confirms
that live order placement is disabled.

The shared C3-only engine writes its current events and outcomes to:

- `/data/bot_events.jsonl`
- `/data/paper_signal_outcomes.jsonl`
- `/data/paper_signal_status.json`

Files matching `/data/c3_live_*` are legacy SHADOW_V2 artifacts. They are not
valid health indicators for the shared C3-only engine.

## Supervision

The runner writes `/data/runtime_heartbeat.json` during startup and throughout
each cycle. The supervisor binds the heartbeat to the runner PID. After a
10-minute startup grace period, a missing, invalid, wrong-PID, or more than
180-second-old heartbeat causes the production workers to exit so Fly can
restart the machine cleanly.

## Legacy archive

Archive legacy V2 artifacts only after a deployment has passed the
authoritative check. Preserve them under `/data/archive/shadow-v2-legacy/`;
do not delete them during rollout.
