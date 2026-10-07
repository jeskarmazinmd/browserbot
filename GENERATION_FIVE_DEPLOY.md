# Deploy G5 paper research

Run on the Mac, from a clean local checkout. The committed Fly configuration enables G5 paper research only; no broker/live-order setting is enabled or altered. G1–G4 remain configured as before.

```bash
cd ~/Desktop/browserbot
git status --short
git switch modular-bot
git pull --ff-only origin modular-bot
fly deploy -a schwab --remote-only
fly status -a schwab
fly ssh console -a schwab
```

If `git status` lists local changes or pull reports a conflict, preserve those changes and inspect before deploying. Do not reset or overwrite them.

Inside the SSH session, after startup:

```bash
cd /app
python -m research_tools.g5_review.verify_production
python -m research_tools.g5_review.report --root /data
```

Compare the source hashes with the reviewed commit. The verification JSON checks 96 registered G5 modules, G3/G4 membership, no failed registry entries, complete durable births/manifest/observations/status, no broker arming, tracker/process freshness, CPU/memory/disk and recent relevant logs. After-hours zero admissions are expected. Production verification must be reviewed; a successful image build alone is insufficient.

G5 activation/coverage begins with deployment, not with the historical training data. Never manufacture old G5 ledger rows. Before births exist, historical reports contain no G5 results. Advisory report data is separate from published performance histories.
