import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SupervisorFactoryIntegrationTests(unittest.TestCase):
    def supervisor_probe(self, enabled=None):
        env = os.environ.copy()

        if enabled is None:
            env.pop(
                "FACTORY_SHADOW_ENABLED",
                None,
            )
        else:
            env[
                "FACTORY_SHADOW_ENABLED"
            ] = enabled

        code = (
            "import supervisor; "
            "print('factory_shadow' "
            "in supervisor.OPTIONAL_WORKERS); "
            "print("
            "supervisor.OPTIONAL_WORKERS"
            ".get('factory_shadow')"
            ")"
        )

        return subprocess.check_output(
            [
                sys.executable,
                "-c",
                code,
            ],
            cwd=ROOT,
            env=env,
            text=True,
        ).strip().splitlines()

    def test_factory_is_off_by_default(self):
        lines = self.supervisor_probe()

        self.assertEqual(
            lines[0],
            "False",
        )

    def test_factory_can_be_enabled(self):
        lines = self.supervisor_probe(
            "1"
        )

        self.assertEqual(
            lines[0],
            "True",
        )

        self.assertIn(
            "research_tools.module_factory."
            "factory_shadow_worker",
            lines[1],
        )

    def test_false_string_stays_disabled(self):
        lines = self.supervisor_probe(
            "false"
        )

        self.assertEqual(
            lines[0],
            "False",
        )

    def test_factory_remains_optional_when_enabled(self):
        env = os.environ.copy()
        env[
            "FACTORY_SHADOW_ENABLED"
        ] = "1"

        code = (
            "import supervisor; "
            "print("
            "supervisor.worker_exit_is_fatal"
            "('factory_shadow')"
            ")"
        )

        result = subprocess.check_output(
            [
                sys.executable,
                "-c",
                code,
            ],
            cwd=ROOT,
            env=env,
            text=True,
        ).strip()

        self.assertEqual(
            result,
            "False",
        )

    def test_dockerfile_copies_factory_package(self):
        dockerfile = (
            ROOT / "Dockerfile"
        ).read_text()

        self.assertIn(
            "COPY research_tools "
            "/app/research_tools",
            dockerfile,
        )


if __name__ == "__main__":
    unittest.main()
