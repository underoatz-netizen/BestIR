"""WP-03 gates: CSD waterfall and spectrogram with persistence metrics."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.adapters import LegacyIRAdapter
from app.extensions.cache import FingerprintCache
from app.extensions.contracts import (AnalysisStatus, AudioBuffer, SourceKey,
                                      PreprocessingConfig, TimeFrequencyConfig)
from app.extensions.csd import compute_csd
from app.extensions.service import ResponseService
from app.extensions.spectrogram import compute_spectrogram
from app.extensions.preprocessing import prepare
from app.core.analysis import analyze_file
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


from app.extensions.preprocessing import prepare  # noqa: E402


def test_slow_80hz_ranks_longer_than_fast_fixture():
    slow = compute_csd(_prep(fx.decay_fixture(80.0, 0.030, n=48000)),
                       TimeFrequencyConfig(profile='balanced'))
    fast = compute_csd(_prep(fx.decay_fixture(80.0, 0.008, n=48000)),
                       TimeFrequencyConfig(profile='balanced'))
    key = 'D20_40-120_ms'
    assert slow.metrics[key + '_valid'] and fast.metrics[key + '_valid'], \
        (slow.metrics, fast.metrics)
    assert slow.metrics[key] > fast.metrics[key] * 1.5


def test_boxy_band_persistence_detected_but_neighbor_not_flagged():
    boxy = compute_spectrogram(_prep(fx.boxy_fixture(300.0, 0.08, n=48000)),
                               TimeFrequencyConfig(profile='balanced'))
    clean = compute_spectrogram(_prep(fx.clean_fixture(n=48000)),
                                TimeFrequencyConfig(profile='balanced'))
    assert boxy.metrics['persistence_valid']
    assert boxy.metrics['persistence_excess_db'] > 3.0
    assert boxy.metrics['persistence_flag'] is True
    # the ridge should sit inside the configured band
    assert 180.0 <= boxy.metrics['persistence_ridge_hz'] <= 500.0
    assert clean.metrics['persistence_excess_db'] < boxy.metrics[
        'persistence_excess_db'] - 3.0


def test_identical_inputs_zero_difference():
    x = fx.boxy_fixture(300.0, 0.05, n=48000)
    a = compute_csd(_prep(x), TimeFrequencyConfig(profile='balanced'))
    b = compute_csd(_prep(x.copy()), TimeFrequencyConfig(profile='balanced'))
    assert np.array_equal(a.magnitude_db, b.magnitude_db)
    assert np.array_equal(a.times_ms, b.times_ms)
    s1 = compute_spectrogram(_prep(x), TimeFrequencyConfig(profile='balanced'))
    s2 = compute_spectrogram(_prep(x.copy()), TimeFrequencyConfig(profile='balanced'))
    assert np.array_equal(s1.magnitude_db, s2.magnitude_db)


def test_result_axes_masks_and_resolution_documented():
    res = compute_csd(_prep(fx.decay_fixture(80.0, 0.02, n=48000)),
                      TimeFrequencyConfig(profile='balanced'))
    nf, nt = res.magnitude_db.shape
    assert len(res.freqs) == nf and len(res.times_ms) == nt
    assert res.freqs[0] >= res.cfg.fmin and res.freqs[-1] <= res.cfg.fmax
    assert res.valid_mask.dtype == bool and len(res.valid_mask) == nf
    assert res.magnitude_db.min() >= -res.cfg.dynamic_range_db - 1e-6
    assert len(res.gate_window_ms) == nt
    assert np.all(np.diff(res.times_ms) > 0)
    assert 'gate_window_ms' in dir(res) and res.gate_window_ms is not None


def test_low_end_claims_suppressed_when_unresolvable():
    # 60 ms useful tail cannot support a 20 dB low-end decay claim: the metric
    # must be reported invalid (gate too short / no decay observable in view)
    x = fx.decay_fixture(100.0, 0.01, n=2880)   # 60 ms
    res = compute_csd(_prep(x), TimeFrequencyConfig(profile='low_end'))
    name = 'D20_40-120_ms'
    assert res.metrics[name + '_valid'] is False
    assert res.metrics[name] is None
    assert res.metrics[name + '_note']


def test_spectrogram_axes_and_mask():
    res = compute_spectrogram(_prep(fx.boxy_fixture(300.0, 0.05, n=48000)),
                              TimeFrequencyConfig(profile='balanced'))
    nf, nt = res.magnitude_db.shape
    assert len(res.freqs) == nf and len(res.times_ms) == nt
    assert res.window_ms > 0 and res.hop_ms > 0
    assert res.valid_mask.dtype == bool


def test_csd_via_service_and_real_file(tmp_path):
    from tests.synth import write_wav
    path = Path(write_wav(tmp_path / 'a.wav', fx.decay_fixture(80.0, 0.02, n=48000)))
    rec = analyze_file(str(path))
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    res = svc.csd(rec)
    assert res.status == AnalysisStatus.OK
    assert res.magnitude_db.shape[0] == len(res.freqs)
    assert res.key.sample_rate == 48000
