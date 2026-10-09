import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from research_tools.g6.export_evidence import DAYS, capture_file, export, ranking, git_revision


EXPECTED = json.loads((Path(__file__).resolve().parents[1] /
                       'research_tools/g6/agreed_ranking_ids.json').read_text())


def history():
    # Descending synthetic returns preserve the supplied identity order.
    return {'days': {day: {'modules': {
        sid: {'return_pct': (498 - i) / 10000, 'taken': i % 7}
        for i, sid in enumerate(EXPECTED)}} for day in DAYS}}


class EvidenceExportTests(unittest.TestCase):
    def test_missing_git_is_optional(self):
        with patch('research_tools.g6.export_evidence.subprocess.run', side_effect=FileNotFoundError):
            self.assertIsNone(git_revision('/app'))
    def test_exact_retirement_boundary_and_missing_day(self):
        h = history()
        del h['days'][DAYS[1]]['modules'][EXPECTED[-1]]
        rows = ranking(h, EXPECTED)
        self.assertEqual(len(rows), 498)
        self.assertEqual(sum(r['decision'] == 'retire' for r in rows), 400)
        self.assertEqual(rows[97]['decision'], 'retain')
        self.assertEqual(rows[98]['decision'], 'retire')
        self.assertEqual(rows[-1]['days_with_records'], 2)
        self.assertIsNone(rows[-1]['daily_returns'][DAYS[1]])

    def test_population_mismatch(self):
        h = history()
        for day in DAYS:
            del h['days'][day]['modules'][EXPECTED[-1]]
        with self.assertRaisesRegex(ValueError, '497'):
            ranking(h, EXPECTED)

    def test_changed_order_blocks_export(self):
        h = history()
        h['days'][DAYS[0]]['modules'][EXPECTED[-1]]['return_pct'] = 99
        with self.assertRaisesRegex(ValueError, 'ranking mismatch'):
            ranking(h, EXPECTED)

    def test_nonfinite_and_missing_returns_rejected(self):
        for value in (None, float('nan'), float('inf'), -101, True):
            h = history()
            h['days'][DAYS[0]]['modules'][EXPECTED[0]]['return_pct'] = value
            with self.assertRaises(ValueError):
                ranking(h, EXPECTED)

    def test_ties_use_module_id(self):
        h = history()
        for day in DAYS:
            for sid in EXPECTED:
                h['days'][day]['modules'][sid]['return_pct'] = 0
        rows = ranking(h, sorted(EXPECTED))
        self.assertEqual([r['module_id'] for r in rows], sorted(EXPECTED))

    def test_export_hashes_and_excludes_credentials_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / 'data'
            data.mkdir()
            history_bytes = json.dumps(history()).encode()
            (data / 'all_engine_bidask_daily_history.json').write_bytes(history_bytes)
            (data / 'schwab_token.json').write_text('credential')
            (data / 'paper_generation_five_bidask_independent_outcomes.jsonl').write_text('{"event_type":"PAPER_ENTRY"}\n')
            output = root / 'bundle.tar.gz'
            export(data, root, output)
            with tarfile.open(output) as archive:
                self.assertFalse(any('token' in n for n in archive.getnames()))
                manifest = json.load(archive.extractfile('manifest.json'))
                record = manifest['sources']['all_engine_bidask_daily_history.json']
                self.assertEqual(record['sha256'], hashlib.sha256(history_bytes).hexdigest())
                self.assertEqual(archive.extractfile('data/all_engine_bidask_daily_history.json').read(), history_bytes)
            self.assertEqual((data / 'all_engine_bidask_daily_history.json').read_bytes(), history_bytes)
            original_archive = output.read_bytes()
            with self.assertRaises(FileExistsError):
                export(data, root, output)
            self.assertEqual(output.read_bytes(), original_archive)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'secret').write_text('secret')
            (root / 'link').symlink_to(root / 'secret')
            with self.assertRaises(ValueError):
                capture_file(root / 'link', root / 'copy')


if __name__ == '__main__':
    unittest.main()
