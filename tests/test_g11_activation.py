import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from research_tools.g11.activate import activate, prefix, PARENTS


class ActivationTests(unittest.TestCase):
    def test_changed_prefix_refuses_activation_and_unchanged_prefix_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);repo=root/'app';repo.mkdir()
            data=b'{"event":"historical"}\n';name='paper_generation_three_outcomes.jsonl'
            ledger=root/name;ledger.write_bytes(data)
            ids=PARENTS+['OLD'+str(i) for i in range(722)]
            (root/'all_engine_performance_live.json').write_text(json.dumps(dict(modules={sid:{} for sid in ids})))
            m=dict(reported_module_ids=ids,consistency='per-file prefixes',source_files={},
                   data_files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())})
            raw=json.dumps(m).encode();sha=hashlib.sha256(raw).hexdigest();archive=root/'evidence.zip'
            (root/'all_engine_bidask_daily_history.json').write_text('{"days":{}}')
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('preservation_manifest.json',raw)
                z.writestr('data/all_engine_bidask_daily_history.json','{"days":{}}')
            (root/'g11_preservation_latest.json').write_text(json.dumps(dict(archive=str(archive))))
            ledger.write_bytes(b'X'+data[1:])
            with patch('shutil.disk_usage',return_value=type('Usage',(),dict(free=1024**3))()):
                with self.assertRaisesRegex(ValueError,'Historical prefix changed'):
                    activate('population',sha,root,repo)
                self.assertFalse((root/'g11_activation.json').exists())
                ledger.write_bytes(data+b'{"event":"newer"}\n')
                before=ledger.read_bytes();r=activate('population',sha,root,repo)
                self.assertTrue(r['historical_prefixes_verified'])
                self.assertEqual(ledger.read_bytes(),before)
                self.assertEqual(activate('population',sha,root,repo)['population_hash'],'population')
    def test_truncated_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'ledger';p.write_bytes(b'row')
            with self.assertRaisesRegex(ValueError,'truncated'):prefix(p,10)
