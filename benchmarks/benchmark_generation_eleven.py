"""Synthetic local cost benchmark; never points at production data."""
from datetime import timedelta
import json
import os
from pathlib import Path
import resource
import tempfile
import time
from unittest.mock import patch
from tests.test_generation_eleven import NOW,BIRTH,activation,quote,signal
from strategies import generation_eleven as g
from generation_eleven_paper_tracker import GenerationElevenTracker
from strategies.generation_eleven_retirement import _activation


def run():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);activation(root)
        with patch.dict(os.environ,ENABLE_G11_PAPER='1',G11_ACTIVATION_PATH=str(root/'g11_activation.json')):
            _activation.cache_clear();started=time.perf_counter()
            t=GenerationElevenTracker(root,now_provider=lambda:BIRTH)
            initialized=time.perf_counter()-started;started=time.perf_counter()
            t.observe_minute(NOW,g.MINUTE_IDS,NOW);t.observe_scan(NOW,100)
            for s in g.CATALOG:
                if not t.register_signal(signal(s.strategy_id),quote(),NOW):raise ValueError(s.strategy_id)
            admission=time.perf_counter()-started;started=time.perf_counter()
            t.snapshot({'XYZ':quote()},NOW)
            size_before=t.ledger_path.stat().st_size
            for i in range(1,11):
                now=NOW+timedelta(minutes=i)
                t.snapshot({'XYZ':quote(now)},now)
            frames=time.perf_counter()-started
            bytes_per_frame=(t.ledger_path.stat().st_size-size_before)/10
            started=time.perf_counter();t.close();t=GenerationElevenTracker(root,now_provider=lambda:NOW+timedelta(minutes=11))
            recovery=time.perf_counter()-started
            result=dict(synthetic=True,population=722,initialized_seconds=initialized,
                admit_722_seconds=admission,eleven_full_frames_seconds=frames,recovery_seconds=recovery,
                bytes_per_account_frame=bytes_per_frame,
                account_frame_estimated_mib_per_390_minute_session=bytes_per_frame*390/1024**2,
                max_rss_host_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                caveat='Frames only; signals/rejections add data. Host RSS units differ on Linux/macOS. Not a production load guarantee.')
            t.close();_activation.cache_clear();return result


if __name__=='__main__':print(json.dumps(run(),indent=2))
