"""Stereo channel policy gates (FINAL_REVIEW 2026-08-31).

The channel policy is decided centrally in ``app.extensions.channel_policy``:
magnitude/energy reductions use the mean of per-channel squares (RMS in
amplitude units), never a signed channel mean, so an anti-phase pair ``[x,-x]``
keeps its energy instead of cancelling to silence.  Phase/group-delay scalars
aggregate only valid channel entries and carry provenance.  Pair blending
rejects channel-count mismatches (no implicit mono<->stereo broadcasting).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.analysis import analyze_file
from app.extensions.cache import FingerprintCache
from app.extensions.channel_policy import channel_count_matches, power_aggregate
from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                      EnvelopeConfig, PhaseConfig,
                                      PreprocessingConfig, SourceKey,
                                      TimeFrequencyConfig)
from app.extensions.csd import compute_csd
from app.extensions.envelope import compute_envelope
from app.extensions.pair_preparation import prepare_pair
from app.extensions.phase import compute_phase
from app.extensions.preprocessing import prepare
from app.extensions.service import ResponseService
from app.extensions.spectrogram import compute_spectrogram
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


# ---- 1. anti-phase [x, -x] is NOT silent ------------------------------------
def test_power_aggregate_antiphase_equals_mono_square():
    x = fx.decay_fixture(120.0, 0.01, n=24000)
    anti = np.stack([x, -x], axis=1)
    np.testing.assert_array_equal(power_aggregate(anti, axis=1), x ** 2)


def test_antiphase_csd_spectrogram_and_envelope_match_mono():
    x = fx.decay_fixture(80.0, 0.02, n=48000)
    mono = _prep(x)
    anti = _prep(np.stack([x, -x], axis=1))
    cfg = TimeFrequencyConfig(profile='balanced')

    c_m = compute_csd(mono, cfg)
    c_a = compute_csd(anti, cfg)
    assert c_m.status == AnalysisStatus.OK and c_a.status == AnalysisStatus.OK
    np.testing.assert_allclose(c_a.magnitude_db, c_m.magnitude_db,
                               atol=1e-9, rtol=0)
    assert c_a.metrics['D20_40-120_ms_valid'] is True
    assert c_a.metrics['D20_40-120_ms'] == c_m.metrics['D20_40-120_ms']

    s_m = compute_spectrogram(mono, cfg)
    s_a = compute_spectrogram(anti, cfg)
    np.testing.assert_allclose(s_a.magnitude_db, s_m.magnitude_db,
                               atol=1e-9, rtol=0)

    e_m = compute_envelope(mono, EnvelopeConfig())
    e_a = compute_envelope(anti, EnvelopeConfig())
    np.testing.assert_allclose(e_a.rms_env, e_m.rms_env, atol=1e-9, rtol=0)
    np.testing.assert_allclose(e_a.hilbert_env, e_m.hilbert_env,
                               atol=1e-9, rtol=0)
    assert abs(e_a.crest_factor - e_m.crest_factor) < 1e-9
    assert abs(e_a.centroid_ms - e_m.centroid_ms) < 1e-9


# ---- 2. L-only [x,0] vs R-only [0,x] phase validity + provenance ------------
def test_l_only_r_only_phase_valid_only_on_active_channel():
    x = fx.decay_fixture(120.0, 0.01, n=24000)
    z = np.zeros_like(x)
    ph_l = compute_phase(_prep(np.stack([x, z], axis=1)), PhaseConfig())
    ph_r = compute_phase(_prep(np.stack([z, x], axis=1)), PhaseConfig())
    ph_a = compute_phase(_prep(np.stack([x, -x], axis=1)), PhaseConfig())

    assert ph_l.status == AnalysisStatus.OK
    # valid only on the active channel (B11 per-channel masks)
    assert ph_l.valid_mask[:, 0].sum() > 0 and ph_l.valid_mask[:, 1].sum() == 0
    assert ph_r.valid_mask[:, 0].sum() == 0 and ph_r.valid_mask[:, 1].sum() > 0
    # anti-phase: both channels carry the same energy -> both valid
    assert ph_a.valid_mask[:, 0].any() and ph_a.valid_mask[:, 1].any()

    # the active-channel GD arrays are computed from the same signal
    np.testing.assert_allclose(ph_l.group_delay_ms[:, 0],
                               ph_r.group_delay_ms[:, 1],
                               rtol=1e-9, atol=1e-9, equal_nan=True)


def test_fingerprint_channel_provenance_and_swapped_gd(tmp_path):
    from tests.synth import write_wav
    x = fx.decay_fixture(120.0, 0.01, n=24000)
    z = np.zeros_like(x)
    p_l = write_wav(tmp_path / 'l_only.wav', np.stack([x, z], axis=1))
    p_r = write_wav(tmp_path / 'r_only.wav', np.stack([z, x], axis=1))
    p_a = write_wav(tmp_path / 'anti.wav', np.stack([x, -x], axis=1))

    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fp_l = svc.fingerprint(analyze_file(p_l))
    fp_r = svc.fingerprint(analyze_file(p_r))
    fp_a = svc.fingerprint(analyze_file(p_a))

    assert fp_l.phase['gd_median_ms'].valid
    assert 'valid channels=(0,)' in fp_l.phase['gd_median_ms'].note
    assert 'valid channels=(1,)' in fp_r.phase['gd_median_ms'].note
    assert 'valid channels=(0,1)' in fp_a.phase['gd_median_ms'].note
    # swapped channels aggregate the same valid evidence -> equal scalar
    assert fp_l.phase['gd_median_ms'].value == pytest.approx(
        fp_r.phase['gd_median_ms'].value, abs=1e-9)


# ---- 3. channel permutation invariance [a,b] vs [b,a] -----------------------
def test_channel_permutation_invariance():
    a = fx.decay_fixture(120.0, 0.01, n=24000)
    b = fx.decay_fixture(220.0, 0.03, n=24000) * 0.5   # scaled: no argmax tie
    ab = _prep(np.stack([a, b], axis=1))
    ba = _prep(np.stack([b, a], axis=1))
    cfg = TimeFrequencyConfig(profile='balanced')

    c_ab = compute_csd(ab, cfg)
    c_ba = compute_csd(ba, cfg)
    np.testing.assert_allclose(c_ba.magnitude_db, c_ab.magnitude_db,
                               rtol=1e-12, atol=1e-12)

    s_ab = compute_spectrogram(ab, cfg)
    s_ba = compute_spectrogram(ba, cfg)
    np.testing.assert_allclose(s_ba.magnitude_db, s_ab.magnitude_db,
                               rtol=1e-12, atol=1e-12)

    e_ab = compute_envelope(ab, EnvelopeConfig())
    e_ba = compute_envelope(ba, EnvelopeConfig())
    np.testing.assert_allclose(e_ba.rms_env, e_ab.rms_env,
                               rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(e_ba.hilbert_env, e_ab.hilbert_env,
                               rtol=1e-12, atol=1e-12)
    assert abs(e_ba.crest_factor - e_ab.crest_factor) < 1e-12
    assert abs(e_ba.centroid_ms - e_ab.centroid_ms) < 1e-12


# ---- 4. mono == [x,x] twin; mono dirac sanity -------------------------------
def test_mono_equals_twin_stereo():
    x = fx.decay_fixture(80.0, 0.02, n=48000)
    mono = _prep(x)
    twin = _prep(np.stack([x, x], axis=1))
    cfg = TimeFrequencyConfig(profile='balanced')

    c_m = compute_csd(mono, cfg)
    c_t = compute_csd(twin, cfg)
    np.testing.assert_allclose(c_t.magnitude_db, c_m.magnitude_db,
                               atol=1e-9, rtol=0)

    s_m = compute_spectrogram(mono, cfg)
    s_t = compute_spectrogram(twin, cfg)
    np.testing.assert_allclose(s_t.magnitude_db, s_m.magnitude_db,
                               atol=1e-9, rtol=0)

    e_m = compute_envelope(mono, EnvelopeConfig())
    e_t = compute_envelope(twin, EnvelopeConfig())
    np.testing.assert_allclose(e_t.rms_env, e_m.rms_env, atol=1e-9, rtol=0)
    np.testing.assert_allclose(e_t.hilbert_env, e_m.hilbert_env,
                               atol=1e-9, rtol=0)
    assert abs(e_t.crest_factor - e_m.crest_factor) < 1e-9
    assert abs(e_t.centroid_ms - e_m.centroid_ms) < 1e-9


def test_mono_dirac_crest_and_peak_time_sanity():
    env = compute_envelope(_prep(fx.dirac(delay_s=0.002)), EnvelopeConfig())
    assert env.crest_factor > 10.0
    # impulse peak sits 1 ms after the kept (1 ms backtracked) onset
    assert abs(env.peak_time_ms - 1.0) <= 0.05


# ---- 5. pair channel mismatch stays INCOMPATIBLE ----------------------------
def test_pair_channel_mismatch_incompatible():
    x = fx.decay_fixture(120.0, 0.01, n=24000)
    mono = _prep(x)
    twin = _prep(np.stack([x, x], axis=1))

    assert not channel_count_matches(mono, twin)
    assert channel_count_matches(mono, mono)
    assert channel_count_matches(twin, twin)

    pair = prepare_pair(mono, twin)
    assert pair.status == AnalysisStatus.INCOMPATIBLE
    assert 'channel' in pair.reason
    pair2 = prepare_pair(twin, mono)
    assert pair2.status == AnalysisStatus.INCOMPATIBLE
    assert 'channel' in pair2.reason