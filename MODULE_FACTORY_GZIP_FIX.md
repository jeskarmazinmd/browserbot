# Module factory gzip resilience fix

This patch prevents a transient `zlib.error` from terminating the paper-only
factory shadow worker while the collector is appending to the compressed quote
archive. The reader fails closed for that cycle, leaves its cursor unchanged,
and retries later.

## Install and test

```bash
cd ~/Desktop/browserbot || exit 1
unzip -o ~/Downloads/module_factory_gzip_resilience_fix_v4_ready.zip -d .
source /tmp/browserbot-test-venv/bin/activate
python -m pytest -q research_tools/module_factory/test_executable_quote_feed.py
fly deploy -a schwab
```

## Verify after deployment

```bash
fly ssh console -a schwab -C \
'python -c "from pathlib import Path; p=Path(\"/data/module_factory/health.json\"); print(p.read_text() if p.exists() else \"NO_FACTORY_HEALTH\")"'
```

The health timestamp should be current and the output should contain the
`adaptive_capacity` section.
