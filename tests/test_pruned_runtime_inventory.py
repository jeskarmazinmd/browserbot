import ast
from pathlib import Path
import unittest

from strategies.registry import FLASH_STRATEGY_MODULES, MINUTE_STRATEGIES


def strategy_id(strategy):
    return str(
        getattr(
            strategy,
            "name",
            getattr(strategy, "STRATEGY_ID", type(strategy).__name__),
        )
    )


def declared_strategies(filename):
    tree = ast.parse(Path(filename).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "STRATEGIES" for target in node.targets):
                return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"STRATEGIES not found in {filename}")


class PrunedRuntimeInventoryTests(unittest.TestCase):
    def test_failed_flash_leaves_are_not_registered(self):
        retired = {"ET29", "PT325", "HT5", "LT65"}
        self.assertFalse(retired & set(FLASH_STRATEGY_MODULES))
        self.assertFalse(retired & {strategy_id(row) for row in MINUTE_STRATEGIES})

    def test_failed_isolated_worker_leaves_are_not_registered(self):
        retired_futures = {"FUTMGC1", "FUTMCL1", "FUTIDXR1", "FUTXAR1"}
        self.assertFalse(retired_futures & set(declared_strategies("futures_shadow_worker.py")))
        self.assertNotIn("SWBREAK10", declared_strategies("swing_shadow_worker.py"))


if __name__ == "__main__":
    unittest.main()
