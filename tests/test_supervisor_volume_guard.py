import unittest
from unittest.mock import patch

import supervisor


class SupervisorVolumeGuardTests(unittest.TestCase):
    def test_reports_filesystem_total_in_mebibytes(self):
        with patch("supervisor.shutil.disk_usage") as usage:
            usage.return_value.total = 2 * 1024 * 1024 * 1024
            self.assertEqual(supervisor.data_volume_total_mb("/data"), 2048)


if __name__ == "__main__":
    unittest.main()
