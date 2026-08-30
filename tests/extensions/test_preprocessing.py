"""WP-02 gates: canonical preparation and envelope/transient metrics."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.adapters import LegacyIRAdapter
from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                      EnvelopeConfig, PreprocessingConfig,
                                      SourceKey)
from app.extensions.envelope import compute_envelope
from app.extensions.preprocessing import prepare
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR, cfg=None):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    key = SourceKey('mem', 0, 0, sr, arr.shape[1])
    return prepare(AudioBuffer(key=key, data=arr), cfg or PreprocessingConfig())


def _env(x, sr=fx.SR):
    return compute_envelope(_prep(x, sr), EnvelopeConfig())


# ---- preprocessing ------------------------------------------------------------
def test_onset_recovered_within_one_sample_on_clean_fixture():
    delay_ms = 3.0
    x = fx.decay_fixture(100.0, 0.02, delay_ms=delay_ms)
    res = _prep(x)
    expected = int(delay_ms / 1000 * fx.SR) - int(1.0 * fx.SR / 1000)  # minus backtrack
    assert abs(res.onset - expected) <= 1
    assert res.status == AnalysisStatus.OK
    assert res.onset_confidence > 0.9
    assert res.peak_value > 0.9


def test_gain_change_does_not_change_normalized_metrics():
    x = fx.decay_fixture(120.0, 0.01)
    a = _env(x)
    b = _env(x * 0.37)
    assert a.peak_time_ms == pytest_approx(b.peak_time_ms)
    assert abs(a.early_energy_5ms - b.early_energy_5ms) < 1e-9
    assert abs(a.centroid_ms - b.centroid_ms) < 1e-9
    assert abs(a.crest_factor - b.crest_factor) < 1e-9
    # absolute metadata follows gain
    pa = _prep(x)
    pb = _prep(x * 0.37)
    assert abs(pa.peak_value - pb.peak_value * (1 / 0.37)) < 1e-9


def pytest_approx(v, tol=1e-9):
    return v


def test_stereo_channels_remain_distinct():
    x = fx.stereo_pair_fixture(delay_samples=7)
    res = _prep(x)
    assert res.channels == 2
    # per-channel data preserved: cross-correlation would find the 7-sample lag
    ch1 = res.data[:, 0]
    ch2 = res.data[:, 1]
    n = 4000
    cc = np.correlate(ch2[:n] - ch2[:n].mean(), ch1[:n] - ch1[:n].mean(), 'full')
    lag = int(np.argmax(np.abs(cc)) - (n - 1))
    assert lag == 7


def test_silent_input_status():
    res = _prep(fx.silent())
    assert res.status == AnalysisStatus.SILENT
    assert res.data is None


def test_nonfinite_input_status():
    res = _prep(fx.with_nan())
    assert res.status == AnalysisStatus.NONFINITE


def test_too_short_input_status():
    res = _prep(np.ones(8))
    assert res.status == AnalysisStatus.TOO_SHORT


def test_clipped_input_warns_but_ok():
    res = _prep(fx.clipped())
    assert res.status == AnalysisStatus.OK
    assert any('clip' in w.lower() for w in res.warnings)


def test_tail_bound_stops_before_file_end_for_decaying_ir():
    res = _prep(fx.decay_fixture(100.0, 0.01, n=24000))
    assert res.tail_end < 23999
    assert res.useful_ms() > 5


# ---- envelope -------------------------------------------------------------------
def test_delayed_dirac_peak_time_and_polarity():
    x = fx.dirac(delay_s=0.004)
    env = _env(x)
    # the impulse peak sits exactly at the pre-backtrack onset, i.e. 1 ms
    # after the kept (backtracked) onset on the onset-relative grid
    assert abs(env.peak_time_ms - 1.0) <= 0.05
    assert env.peak_polarity == 1


def test_inverted_dirac_polarity():
    env = _env(fx.dirac(delay_s=0.003, invert=True))
    assert env.peak_polarity == -1


def test_rise_time_invalid_for_one_sample_peak():
    env = _env(fx.dirac(delay_s=0.003))
    assert env.rise_valid is False
    assert env.rise_time_ms is None
    assert 'one-sample' in env.rise_reason or 'short' in env.rise_reason


def test_rise_time_valid_for_attack_envelope():
    env = _env(fx.attack_fixture(attack_ms=1.0))
    assert env.rise_valid is True
    assert 0.1 < env.rise_time_ms < 1.6   # hann ramp 10-90% of a 1 ms ramp


def test_rise_time_invalid_for_one_pole_decay_response():
    # a one-pole impulse response peaks at its first sample: no attack to measure
    env = _env(fx.lowpassed_click(1500))
    assert env.rise_valid is False
    assert env.rise_time_ms is None


def test_early_energy_ratios_bounded():
    env = _env(fx.decay_fixture(100.0, 0.02, n=24000))
    assert 0.0 <= env.early_energy_1ms <= 1.0
    assert env.early_energy_5ms >= env.early_energy_1ms
    assert env.early_late_ratio is not None and env.early_late_ratio > 0


def test_crest_factor_of_dirac_is_high():
    env = _env(fx.dirac(delay_s=0.002))
    assert env.crest_factor > 10.0
