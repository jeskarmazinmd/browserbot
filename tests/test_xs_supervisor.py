import unittest
from pathlib import Path

import supervisor


class XSResearchSupervisorTests(unittest.TestCase):
    def test_xs_shadow_is_optional_but_production_workers_are_fatal(self):
        self.assertIn("xs_shadow", supervisor.OPTIONAL_WORKERS)
        self.assertFalse(supervisor.worker_exit_is_fatal("xs_shadow"))
        for name in supervisor.WORKERS:
            self.assertTrue(supervisor.worker_exit_is_fatal(name), name)

    def test_xs_shadow_has_no_overlap_with_production_worker_names(self):
        self.assertFalse(set(supervisor.WORKERS) & set(supervisor.OPTIONAL_WORKERS))

    def test_docker_image_contains_market_and_xs_runtime_dependencies(self):
        dockerfile=Path("Dockerfile").read_text()
        for required in (
            "COPY market_quotes.py .",
            "COPY market_evidence.py .",
            "COPY xs_shadow_worker.py .",
            "COPY research_lab /app/research_lab",
        ):
            self.assertIn(required,dockerfile)


if __name__ == "__main__":
    unittest.main()
