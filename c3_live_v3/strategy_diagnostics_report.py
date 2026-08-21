"""Render the compact strategy runtime diagnostics snapshot."""

import json
from pathlib import Path


def main():
    path = Path("/data/strategy_runtime_diagnostics.json")
    if not path.exists():
        print(f"diagnostics unavailable: {path} does not exist")
        return 1
    payload = json.loads(path.read_text())
    print("STRATEGY RUNTIME DIAGNOSTICS")
    print(f"Updated: {payload.get('updated_at')}")
    print()
    print(f"{'Module':<9}{'Status':<17}{'Cycles':>9}{'Symbols':>10}{'Signals':>9}{'Errors':>8}  Nearest / explanation")
    print("-" * 112)
    for strategy_id, row in payload.get("modules", {}).items():
        nearest = row.get("nearest_miss")
        if nearest:
            failed_rules = nearest.get("failed_rules")
            if failed_rules:
                parts = []
                for rule in failed_rules:
                    observed = rule.get("observed")
                    required = rule.get("required")
                    unit = rule.get("unit", "")
                    kind = rule.get("kind")
                    relation = {"minimum": ">=", "maximum": "<=", "between": "within", "boolean": "is"}.get(kind, "vs")
                    parts.append(f"{rule.get('rule')}={observed}{unit} required {relation} {required}{unit}")
                failed = "; ".join(parts)
            else:
                failed = nearest.get("failed") or "threshold shortfall"
            inherited = f" via {nearest.get('inherited_from_parent')}" if nearest.get("inherited_from_parent") else ""
            detail = f"{nearest.get('symbol', '—')}{inherited}: {failed} (score={nearest.get('miss_score', '—')})"
        elif row.get("status") == "WAITING_PARENT":
            detail = f"waiting for {row.get('parent_strategy')} signal"
        elif row.get("status") == "INACTIVE":
            detail = row.get("reason", "not connected")
        else:
            detail = row.get("nearest_miss_status", "no candidate recorded yet")
        print(
            f"{strategy_id:<9}{row.get('status', 'UNKNOWN'):<17}"
            f"{int(row.get('evaluation_cycles', 0)):>9}"
            f"{int(row.get('last_symbol_count', 0)):>10}"
            f"{int(row.get('signals', 0)):>9}"
            f"{int(row.get('errors', 0)):>8}  {detail}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
