"""WP-01 adapter + service tests that need a legacy record object."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.analysis import analyze_file
from app.extensions.cache import FingerprintCache
from app.extensions.service import ResponseService
from tests.synth import synth_ir, write_wav


def test_service_load_matches_legacy_record(tmp_path):
    path = Path(write_wav(tmp_path / 'a.wav', synth_ir(seed=7), 48000))
    rec = analyze_file(str(path))
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    buf = svc.load(rec)
    assert Path(buf.key.path) == path.resolve()
    assert buf.sample_rate == rec.sample_rate


def test_service_load_does_not_mutate_record(tmp_path):
    path = Path(write_wav(tmp_path / 'a.wav', synth_ir(seed=8), 48000))
    rec = analyze_file(str(path))
    before = (rec.curve_db.copy(), rec.score)
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    svc.load(rec)
    assert np.array_equal(rec.curve_db, before[0]) and rec.score is None
