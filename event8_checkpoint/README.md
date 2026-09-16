# Event8 prospective research family

This checkpoint installs eight paper-only event strategies and a read-only Schwab quote worker. It never places broker orders.

The worker deliberately starts as `WAITING_EVENT_FEED`. Supply `/data/event_feed.jsonl` (or set `EVENT_FEED_PATH`) with one JSON object per line:

```json
{"event_id":"provider-unique-id","published_at":"2026-08-10T12:01:02+00:00","observed_at":"2026-08-10T12:01:05+00:00","symbol":"XYZ","event_type":"EARNINGS","direction":"POSITIVE","magnitude":0.12,"source":"provider-name","source_url":"https://provider.example/event/unique-id"}
```

Allowed strategy event types are `EARNINGS`, `GUIDANCE`, `SEC_8K`, `ANALYST_REVISION`, and `MACRO_RELEASE`. `direction` is `POSITIVE` or `NEGATIVE`. `magnitude` is a source-defined normalized surprise strength and must be documented by the eventual adapter.

The worker rejects missing provenance, invalid/naive timestamps, events observed before publication, future observations, stale records, and non-HTTPS source URLs. No sample event is installed into production data because synthetic events would contaminate prospective results.
