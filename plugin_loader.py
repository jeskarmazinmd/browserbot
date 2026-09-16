from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_plugin(plugin_root, expected_strategy_id, expected_hash):
    root = Path(plugin_root)
    manifest = json.loads((root / "manifest.json").read_text())
    strategy_path = root / "strategy.py"
    actual_hash = file_hash(strategy_path)
    if manifest.get("strategy_id") != expected_strategy_id:
        raise RuntimeError("plugin strategy ID does not match allowlist")
    if expected_hash and actual_hash != expected_hash:
        raise RuntimeError("plugin file hash does not match allowlist")
    spec = importlib.util.spec_from_file_location(
        f"executor_plugin_{expected_strategy_id.lower()}", strategy_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin = module.create_plugin()
    if str(plugin.strategy_id) != expected_strategy_id:
        raise RuntimeError("plugin runtime ID does not match manifest")
    return plugin, manifest, actual_hash
