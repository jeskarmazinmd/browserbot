import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from research_tools.g11.preserve import preserve


class PreservationTests(unittest.TestCase):
    def test_evidence_is_hashed_and_originals_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'data'
            repo = Path(directory) / 'app'
            root.mkdir(); (repo / 'strategies').mkdir(parents=True)
            inputs = {'all_engine_bidask_daily_history.json': b'{"days":{}}',
                      'all_engine_performance_live.json': b'{"as_of":"reference","modules":{"PARENT":{}}}',
                      'all_engine_performance_health.json': b'{}',
                      'paper_generation_nine_outcomes.jsonl': b'{"event":"test"}\n'}
            for name, data in inputs.items():
                (root / name).write_bytes(data)
            (root / 'secret_tokens.json').write_text('do not export')
            (repo / 'strategies' / 'parent.py').write_text('PAPER_ONLY=True\n')
            result = preserve(root, repo)
            with zipfile.ZipFile(result['archive']) as z:
                manifest = json.loads(z.read('preservation_manifest.json'))
                self.assertEqual(result['reported_module_count'], 1)
                self.assertNotIn('data/secret_tokens.json', z.namelist())
                self.assertIn('app/strategies/parent.py', z.namelist())
                for name, data in inputs.items():
                    self.assertEqual((root / name).read_bytes(), data)
                    self.assertEqual(z.read('data/' + name), data)
                    self.assertEqual(manifest['data_files'][name]['sha256'], hashlib.sha256(data).hexdigest())

    def test_missing_required_evidence_fails_before_creating_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Missing required'):
                preserve(directory, directory)
            self.assertFalse((Path(directory) / 'g11_preservation').exists())
