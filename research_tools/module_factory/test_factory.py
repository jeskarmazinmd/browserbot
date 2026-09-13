import unittest
from datetime import datetime, timedelta, timezone

from research_tools.cascade_reversal_study import Bar
from research_tools.module_factory.factory import (
    Candidate,
    generate_candidates,
)


class ModuleFactoryTests(unittest.TestCase):
    def test_candidate_ids_are_deterministic(self):
        candidate = generate_candidates()[0]
        self.assertEqual(candidate.candidate_id, candidate.candidate_id)
        self.assertTrue(candidate.candidate_id.startswith("MF-"))

    def test_generator_contains_both_directions(self):
        candidates = generate_candidates()
        directions = {candidate.direction for candidate in candidates}
        self.assertEqual(directions, {"long", "short"})

    def test_generator_has_unique_ids(self):
        candidates = generate_candidates()
        ids = [candidate.candidate_id for candidate in candidates]
        self.assertEqual(len(ids), len(set(ids)))

    def test_factory_candidates_are_research_objects_only(self):
        candidate = generate_candidates()[0]
        self.assertEqual(candidate.family, "cascade")
        self.assertFalse(hasattr(candidate, "place_order"))
        self.assertFalse(hasattr(candidate, "trade"))


if __name__ == "__main__":
    unittest.main()
