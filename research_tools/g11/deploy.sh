#!/usr/bin/env bash
# Run from the reviewed Mac checkout; source edits never occur over SSH.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "$(git branch --show-current)" != modular-bot || -n "$(git status --porcelain)" ]]; then
  echo 'G11 requires a clean, committed modular-bot checkout.' >&2
  exit 1
fi
G11_REVISION="$(git rev-parse HEAD)"
python3 -m research_tools.g11.run_checks
# Publishing Git must precede production activation and deployment.
git push origin modular-bot
G11_HASH="$(python3 -c 'from strategies.generation_eleven import POPULATION_HASH; print(POPULATION_HASH)')"
G11_MANIFEST="$(python3 -c 'from strategies.generation_eleven_retirement import plan; print(plan()["evidence_manifest_sha256"])')"
# Verify the downloaded off-machine preservation copy, not only the volume copy.
python3 - "$G11_MANIFEST" "${G11_LOCAL_ARCHIVE:-$HOME/Desktop/g11-production-evidence.zip}" <<'PYVERIFY'
import hashlib,sys,zipfile
with zipfile.ZipFile(sys.argv[2]) as z:
    assert z.testzip() is None, 'Local preservation archive CRC failure'
    assert hashlib.sha256(z.read('preservation_manifest.json')).hexdigest()==sys.argv[1], 'Wrong local preservation archive'
print('Off-machine preservation copy verified')
PYVERIFY
G11_GATE="$(python3 research_tools/g8/remote_command.py research_tools/g11/activate.py --population-hash "$G11_HASH" --manifest-sha "$G11_MANIFEST")"
fly ssh console -a schwab --machine 7813422f149398 -C "$G11_GATE"
fly deploy -a schwab --strategy immediate \
  --build-arg "G6_BUILD_REVISION=$G11_REVISION" \
  --build-arg "G7_BUILD_REVISION=$G11_REVISION" \
  --build-arg "G8_BUILD_REVISION=$G11_REVISION" \
  --build-arg "G9_BUILD_REVISION=$G11_REVISION" \
  --build-arg "G10_BUILD_REVISION=$G11_REVISION" \
  --build-arg "G11_BUILD_REVISION=$G11_REVISION"
fly status -a schwab
fly ssh console -a schwab --machine 7813422f149398 -C "python -m research_tools.g11.verify_production --allow-warmup --expected-revision $G11_REVISION"
echo 'After reporting refresh, verify exact 734 outputs and observed data paths:'
echo 'fly ssh console -a schwab --machine 7813422f149398 -C "python -m research_tools.g11.verify_production"'
