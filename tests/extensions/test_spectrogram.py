"""B15 gates: shared-grid spectrogram comparison (pure, no Qt)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AnalysisStatus, AudioBuffer, SourceKey,
                                      PreprocessingConfig, SpectrogramResult,
                                      TimeFrequencyConfig)
from app.extensions.preprocessing import prepare
from app.extensions.spectrogram import (compare_spectrograms,
                                        compute_spectrogram, spectrogram_error)
from app.extensions.time_frequency import log_freq_grid
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


def _hand(freqs, times, status=AnalysisStatus.OK, valid=None, mag=None):
    fa = np.asarray(freqs, dtype=float)
    ta = np.asarray(times, dtype=float)
    if mag is None:
        mag = np.zeros((len(fa), len(ta)), dtype=float)
    return SpectrogramResult(
        key=SourceKey('hand', 0, 0, 48000, 1), cfg=TimeFrequencyConfig(),
        status=status, freqs=fa, times_ms=ta, magnitude_db=mag,
        valid_mask=valid if valid is not None
        else np.ones(len(fa), dtype=bool))


def _blob(freqs, times, f0=300.0, t0=20.0, fw=0.15, tw=3.0):
    """Smooth 0 dB-peak blob used as a known tone/time oracle."""
    return (-(np.log2(freqs[:, None] / f0) / fw) ** 2 * 10.0
            - ((times[None, :] - t0) / tw) ** 2)


# ---------------------------------------------------------------------------
# 78-ish vs 4 frames: valid difference over the physical overlap
# ---------------------------------------------------------------------------

def test_many_vs_few_frames_produce_valid_difference_over_overlap():
    cfg = TimeFrequencyConfig(profile='balanced')
    long_spec = compute_spectrogram(
        _prep(fx.boxy_fixture(300.0, 0.08, n=24000)), cfg)
    short_spec = compute_spectrogram(
        _prep(fx.decay_fixture(300.0, 0.02, n=1536)), cfg)
    assert len(long_spec.times_ms) >= 4 * len(short_spec.times_ms)
    assert len(short_spec.times_ms) <= 8

    cmp = compare_spectrograms(long_spec, short_spec)
    assert cmp.available, cmp.reason
    assert cmp.diff_db is not None and cmp.valid_diff is not None
    assert cmp.diff_db.shape == (len(cmp.freqs), len(cmp.times_ms))
    # shared grid = the physical overlap: max(A start, B start) .. min(A end, B end)
    assert np.isclose(cmp.times_ms[0], max(long_spec.times_ms[0],
                                           short_spec.times_ms[0]))
    assert np.isclose(cmp.times_ms[-1], min(long_spec.times_ms[-1],
                                            short_spec.times_ms[-1]))
    assert np.isclose(cmp.freqs[0], max(long_spec.freqs[0], short_spec.freqs[0]))
    assert np.isclose(cmp.freqs[-1], min(long_spec.freqs[-1], short_spec.freqs[-1]))
    assert bool(cmp.valid_diff.any())
    assert np.all(np.isfinite(cmp.diff_db[cmp.valid_diff]))
    # both sides were resampled onto the identical shared grid
    assert cmp.magnitude_a_db.shape == cmp.magnitude_b_db.shape \
        == cmp.diff_db.shape


def test_identical_inputs_zero_difference_on_shared_grid():
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    s1 = compute_spectrogram(_prep(x), TimeFrequencyConfig(profile='balanced'))
    s2 = compute_spectrogram(_prep(x.copy()), TimeFrequencyConfig(profile='balanced'))
    cmp = compare_spectrograms(s1, s2)
    assert cmp.available
    assert np.allclose(cmp.diff_db[cmp.valid_diff], 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# Different sample rates / grids preserve a known tone and time location
# ---------------------------------------------------------------------------

def test_different_sample_rates_preserve_known_tone_and_time():
    cfg = TimeFrequencyConfig(profile='balanced')
    s48 = compute_spectrogram(
        _prep(fx.decay_fixture(300.0, 0.03, n=12000, sr=48000, delay_ms=2.0),
              sr=48000), cfg)
    s44 = compute_spectrogram(
        _prep(fx.decay_fixture(300.0, 0.03, n=11025, sr=44100, delay_ms=2.0),
              sr=44100), cfg)
    assert not np.array_equal(s48.times_ms, s44.times_ms)

    cmp = compare_spectrograms(s48, s44)
    assert cmp.available, cmp.reason
    for mag, valid in ((cmp.magnitude_a_db, cmp.valid_a),
                       (cmp.magnitude_b_db, cmp.valid_b)):
        m = np.where(valid, mag, -np.inf)
        fi, ti = np.unravel_index(np.argmax(m), m.shape)
        # tone frequency preserved within a few shared bins of 300 Hz
        assert abs(cmp.freqs[fi] - 300.0) < 40.0
        # first-frame window centre ~= 10.7 ms after the 2 ms-delayed onset
        assert abs(cmp.times_ms[ti] - 10.7) < 8.0


def test_different_grids_preserve_analytic_tone_and_time():
    ga = log_freq_grid(50, 20000, 24)
    ta = np.linspace(0, 200, 78)
    gb = log_freq_grid(50, 20000, 18)
    tb = np.linspace(5, 120, 30)
    ha = _hand(ga, ta, mag=_blob(ga, ta))
    hb = _hand(gb, tb, mag=_blob(gb, tb))
    cmp = compare_spectrograms(ha, hb)
    assert cmp.available, cmp.reason
    step_t = cmp.times_ms[1] - cmp.times_ms[0]
    for mag, valid in ((cmp.magnitude_a_db, cmp.valid_a),
                       (cmp.magnitude_b_db, cmp.valid_b)):
        m = np.where(valid, mag, -np.inf)
        fi, ti = np.unravel_index(np.argmax(m), m.shape)
        assert abs(np.log2(cmp.freqs[fi] / 300.0)) <= 1.0 / 24.0 + 1e-9
        assert abs(cmp.times_ms[ti] - 20.0) <= step_t + 1e-9


# ---------------------------------------------------------------------------
# Swap A/B negates the difference while preserving axes/reference
# ---------------------------------------------------------------------------

def test_swap_negates_difference_and_preserves_grid_and_reference():
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    s1 = compute_spectrogram(_prep(x), TimeFrequencyConfig(profile='balanced'))
    s2 = compute_spectrogram(_prep(x * 0.5), TimeFrequencyConfig(profile='balanced'))
    c1 = compare_spectrograms(s1, s2)
    c2 = compare_spectrograms(s2, s1)
    assert c1.available and c2.available
    assert np.array_equal(c1.freqs, c2.freqs)
    assert np.array_equal(c1.times_ms, c2.times_ms)
    assert c1.ref_db == c2.ref_db
    assert c1.overlap_time_ms == c2.overlap_time_ms
    assert c1.overlap_freq_hz == c2.overlap_freq_hz
    assert np.array_equal(c1.valid_diff, c2.valid_diff)
    assert np.allclose(c1.diff_db, -c2.diff_db, atol=1e-9)


# ---------------------------------------------------------------------------
# No-overlap and malformed inputs return an explicit reason
# ---------------------------------------------------------------------------

def test_no_overlap_reasons_are_explicit():
    ga = log_freq_grid(50, 20000, 24)
    t_a = np.linspace(0, 100, 20)
    t_b = np.linspace(200, 300, 20)
    cmp = compare_spectrograms(_hand(ga, t_a), _hand(ga, t_b))
    assert not cmp.available
    assert 'time' in cmp.reason and 'overlap' in cmp.reason

    lo = log_freq_grid(20, 1000, 24)
    hi = log_freq_grid(2000, 20000, 24)
    t = np.linspace(0, 100, 20)
    cmp = compare_spectrograms(_hand(lo, t), _hand(hi, t))
    assert not cmp.available
    assert 'frequency' in cmp.reason and 'overlap' in cmp.reason


@pytest.mark.parametrize('bad', [
    'silent',           # analysis failure status
    'too_short',
    'nonfinite',
])
def test_malformed_side_reports_explicit_reason(bad):
    ga = log_freq_grid(50, 20000, 24)
    good = _hand(ga, np.linspace(0, 100, 20))
    bad_spec = _hand(ga, np.linspace(0, 100, 20),
                     status=AnalysisStatus(bad), mag=None)
    cmp = compare_spectrograms(good, bad_spec)
    assert not cmp.available
    assert 'IR B' in cmp.reason and 'unavailable' in cmp.reason
    assert bad.replace('_', ' ') in cmp.reason


def test_shape_mismatch_reports_malformed_data():
    ga = log_freq_grid(50, 20000, 24)
    t = np.linspace(0, 100, 20)
    bad = _hand(ga, t, mag=np.zeros((len(ga), 7), dtype=float))
    assert 'does not match' in spectrogram_error(bad)
    cmp = compare_spectrograms(bad, _hand(ga, t))
    assert not cmp.available
    assert 'unavailable' in cmp.reason and 'does not match' in cmp.reason


def test_none_input_has_explicit_reason():
    cmp = compare_spectrograms(None, None)
    assert not cmp.available
    assert 'unavailable' in cmp.reason
    assert cmp.magnitude_a_db is None and cmp.diff_db is None


def test_all_invalid_bins_in_overlap_reported():
    ga = log_freq_grid(50, 20000, 24)
    t = np.linspace(0, 100, 20)
    valid = np.zeros(len(ga), dtype=bool)
    cmp = compare_spectrograms(_hand(ga, t, valid=valid), _hand(ga, t))
    assert not cmp.available
    assert 'reliable' in cmp.reason