from types import SimpleNamespace
import unittest

from research_tools.module_factory.causal_compiler import compile_frozen_hypothesis


class CausalCompilerTests(unittest.TestCase):
    def test_explicit_rule_from_future_scientist_compiles(self):
        specification = SimpleNamespace(
            scientist="future_causal", features=("return_5",), horizon=5,
            direction=1,
            parameters={"generated_rules": [{
                "label": "EDGE", "direction": 1,
                "predicate": {"op": "gt",
                    "left": {"op": "feature", "name": "return_5"},
                    "right": {"op": "constant", "value": 0.25}},
            }]},
        )
        frozen = SimpleNamespace(
            specification=specification, hypothesis_id="hypothesis:abc123",
            specification_hash="frozen-hash",
        )
        compiled = compile_frozen_hypothesis(frozen)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0].scientist, "future_causal")
        self.assertEqual(compiled[0].module_id, "FM_ABC123_EDGE")
