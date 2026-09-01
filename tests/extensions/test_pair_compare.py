"""WP-04 gates: phase, group delay, pair alignment, blend prediction."""
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AnalysisStatus, PairComparisonConfig,
                                      PairComparisonResult, PhaseConfig)
from app.extensions.pair_compare import compare_pair, predict_blend
from app.extensions.phase import compute_phase
from app.extensions.preprocessing import prepare
from app.extensions.processing import blend_sum
from app.extensions.contracts import AudioBuffer, SourceKey
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfigLazy())


def PreprocessingConfigLazy():
    from app.extensions.contracts import PreprocessingConfig
    return PreprocessingConfig()


def _full_buffer_delayed_pair(delay_samples=96):
    n = 2048
    start = 256
    rng = np.random.default_rng(17)
    response = rng.standard_normal(720) * np.exp(-np.arange(720) / 260.0)
    response[0] = 1.0
    a = np.zeros(n, dtype=np.float64)
    a[start:start + len(response)] = response
    b = np.zeros_like(a)
    b[delay_samples:] = a[:-delay_samples]
    return a, b, delay_samples


def _spectrum_rms_error(predicted_db, actual_db):
    reliable = (predicted_db > predicted_db.max() - 50.0) & \
        (actual_db > actual_db.max() - 50.0)
    return float(np.sqrt(np.mean((predicted_db[reliable] - actual_db[reliable]) ** 2)))


def _ratio_cancellation_loss(prediction, ratio):
    evidence_by_ratio = getattr(prediction, 'risk_by_ratio', None)
    assert isinstance(evidence_by_ratio, Mapping), (
        'BlendPrediction must expose public ratio-keyed cancellation evidence'
    )
    assert ratio in evidence_by_ratio
    evidence = evidence_by_ratio[ratio]
    if isinstance(evidence, Mapping):
        loss = evidence.get('worst_cancellation_db')
    else:
        loss = getattr(evidence, 'worst_cancellation_db', None)
    assert loss is not None
    return float(loss)


def _inverse_polarity_loss_db(ratio_b):
    """Independent power-sum deficit for equal, opposite-polarity sources."""
    gain_a, gain_b = 1.0 - ratio_b, ratio_b
    expected = np.hypot(gain_a, gain_b)
    actual = max(abs(gain_a - gain_b), 1e-30)
    return float(20.0 * np.log10(expected / actual))


# ---- phase ---------------------------------------------------------------------
def test_pure_delay_group_delay_matches_injected_delay():
    # delayed dirac: after onset alignment the impulse sits 1 ms after time
    # zero (the kept 1 ms pre-onset) -> group delay ~1 ms
    x = fx.dirac(delay_s=0.005)
    res = compute_phase(_prep(x), PhaseConfig())
    assert res.status == AnalysisStatus.OK
    gd = res.group_delay_ms[:, 0][res.valid_mask[:, 0]]
    assert 0.6 < np.nanmedian(gd) < 1.4, np.nanmedian(gd)
    assert res.coverage > 0.0


def test_unreliable_bins_masked_not_interpolated():
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    res = compute_phase(_prep(x), PhaseConfig(rel_threshold_db=-40.0))
    nan_bins = np.isnan(res.phase_rad[:, 0])
    assert nan_bins.sum() > 0
    assert np.all(np.isnan(res.phase_rad[nan_bins, 0]))
    valid_now = ~nan_bins
    assert np.all(res.valid_mask[:, 0][valid_now])


def test_min_and_excess_phase_sum_to_total():
    x = fx.lowpassed_click(1500, n=24000)
    res = compute_phase(_prep(x), PhaseConfig(min_phase=True))
    ok = res.valid_mask[:, 0] & np.isfinite(res.min_phase_rad[:, 0]) \
        & np.isfinite(res.excess_phase_rad[:, 0])
    assert ok.sum() > 100
    total = res.phase_rad[ok, 0]
    parts = res.min_phase_rad[ok, 0] + res.excess_phase_rad[ok, 0]
    dphi = np.angle(np.exp(1j * (total - parts)))
    assert np.max(np.abs(dphi)) < 1e-6


# ---- pair alignment ---------------------------------------------------------------
def _raw_delay_estimate(xa, xb):
    from app.extensions.pair_compare import _estimate_delay
    d, conf = _estimate_delay(xa, xb, fx.SR, PairComparisonConfig())
    return d, conf


def test_integer_delay_exact_on_raw_windows():
    delay = 31   # samples
    x = fx.boxy_fixture(300.0, 0.02, n=24000)   # broadband fixture
    lo, hi = 96, 20000            # identical window bounds -> shift preserved
    xa, xb = x[lo:hi], np.concatenate([np.zeros(delay), x[lo:hi - delay]])
    d, conf = _raw_delay_estimate(xa, xb)
    assert abs(d - delay) <= 0.1
    assert conf > 0.5


def test_fractional_delay_error_under_quarter_sample():
    true_frac = 31.4
    x = fx.boxy_fixture(300.0, 0.05, n=24000)   # agreed broadband fixture
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fx.SR)
    shifted = np.fft.irfft(X * np.exp(-2j * np.pi * f * true_frac / fx.SR), n)
    lo, hi = 96, 20000
    xa, xb = x[lo:hi], shifted[lo:hi]
    d, _ = _raw_delay_estimate(xa, xb)
    assert abs(d - true_frac) <= 0.25, d


def test_polarity_sign_on_prepared_pair():
    x = fx.decay_fixture(150.0, 0.02, n=24000)
    res = compare_pair(_prep(x), _prep(-x.copy()), PairComparisonConfig())
    assert res.polarity == -1
    res_same = compare_pair(_prep(x), _prep(x.copy()), PairComparisonConfig())
    assert res_same.polarity == 1


def test_phase_diff_weighted_low_for_identical():
    x = fx.decay_fixture(150.0, 0.02, n=24000)
    res = compare_pair(_prep(x), _prep(x.copy()), PairComparisonConfig())
    assert res.phase_diff_weighted_rms_deg < 10.0


# ---- B10: phase-diff RMS uses exactly one square root -------------------------
def test_b10_inverted_pair_phase_diff_is_180_deg():
    """Inverted pair -> ~180 deg weighted phase difference on reliable bins.

    The weighted RMS is already a root-mean-square; a second square root
    (the B10 bug) would collapse pi radians to sqrt(pi) ~= 101.9 deg.
    """
    x = fx.decay_fixture(150.0, 0.02, n=24000)
    res = compare_pair(_prep(x), _prep(-x.copy()), PairComparisonConfig())
    assert res.status == AnalysisStatus.OK
    assert res.polarity == -1
    assert 175.0 < res.phase_diff_weighted_rms_deg < 185.0, \
        res.phase_diff_weighted_rms_deg


def test_b10_empty_risk_band_reports_zero_valid_fraction_and_nan_phase_diff():
    """A band with no reliable bins must not fabricate a phase-diff value."""
    x = fx.decay_fixture(150.0, 0.02, n=24000)   # energy sits far below band
    cfg = PairComparisonConfig(risk_band=(20000.0, 24000.0))
    res = compare_pair(_prep(x), _prep(x.copy()), cfg)
    assert res.status == AnalysisStatus.OK
    assert res.valid_fraction == 0.0
    assert np.isnan(res.phase_diff_weighted_rms_deg)


# ---- B11: per-channel validity ------------------------------------------------
def test_b11_silent_stereo_channel_keeps_own_nan_mask_phase_and_gd():
    """A silent channel never inherits validity from an active neighbour."""
    active = fx.decay_fixture(150.0, 0.02, n=24000)
    stereo = np.column_stack([active, np.zeros_like(active)])
    res = compute_phase(_prep(stereo), PhaseConfig())
    assert res.status == AnalysisStatus.OK
    assert res.valid_mask is not None and res.phase_rad is not None
    assert res.group_delay_ms is not None
    assert res.valid_mask[:, 1].sum() == 0              # silent: nothing valid
    assert np.all(np.isnan(res.phase_rad[:, 1]))
    assert np.all(np.isnan(res.group_delay_ms[:, 1]))
    assert res.valid_mask[:, 0].sum() > 0               # active: own real coverage
    assert not np.all(np.isnan(res.phase_rad[:, 0]))
    assert not np.all(np.isnan(res.group_delay_ms[:, 0]))


# ---- full-buffer pair timing ----------------------------------------------------
def test_b03_compare_pair_keeps_leading_silence_in_total_delay():
    a, b, delay = _full_buffer_delayed_pair()
    pa, pb = _prep(a), _prep(b)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    cfg = PairComparisonConfig()
    pair = compare_pair(pa, pb, cfg)
    swapped = compare_pair(pb, pa, cfg)

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    assert pair.status == swapped.status == AnalysisStatus.OK
    assert (
        pair.delay_samples > 0.0 and
        abs(pair.delay_samples - delay) <= 0.25 and
        swapped.delay_samples < 0.0 and
        abs(swapped.delay_samples + delay) <= 0.25
    ), (f'B-later={pair.delay_samples:.3f}, '
        f'swapped={swapped.delay_samples:.3f}, expected +/-{delay}')


def test_b03_blend_sum_advances_b_by_the_total_full_buffer_delay():
    a, b, _ = _full_buffer_delayed_pair()
    pa, pb = _prep(a), _prep(b)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    pair = compare_pair(pa, pb, PairComparisonConfig())
    mix, sample_rate, _ = blend_sum(pa, pb, pair, ratio_b=1.0)

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    expected_peak = int(np.argmax(np.abs(a_before[:, 0])))
    actual_peak = int(np.argmax(np.abs(mix[:, 0])))
    lo = max(0, expected_peak - 64)
    hi = min(pa.frames, expected_peak + 384)
    correlation = float(np.corrcoef(mix[lo:hi, 0], a_before[lo:hi, 0])[0, 1])
    assert sample_rate == pa.sample_rate
    assert abs(actual_peak - expected_peak) <= 1, (actual_peak, expected_peak)
    assert correlation > 0.995, correlation


def test_b03_suggested_prediction_matches_processed_full_buffer_spectrum():
    a, b, _ = _full_buffer_delayed_pair()
    pa, pb = _prep(a), _prep(b)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    cfg = PairComparisonConfig(blend_ratios=(0.5,))
    pair = compare_pair(pa, pb, cfg)
    prediction = predict_blend(pa, pb, cfg, alignment='suggested')
    mix, sample_rate, _ = blend_sum(pa, pb, pair, ratio_b=0.5)
    nfft = (len(prediction.freqs) - 1) * 2
    actual_db = 20.0 * np.log10(np.maximum(
        np.abs(np.fft.rfft(mix[:, 0], nfft)), 1e-30))

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    assert prediction.status == AnalysisStatus.OK
    assert sample_rate == pa.sample_rate
    error = _spectrum_rms_error(prediction.magnitude_db[0], actual_db)
    assert error < 0.25, f'{error:.3f} dB with delay {pair.delay_samples:.3f}'


# ---- invalid pair propagation ----------------------------------------------------
def test_b07_silent_b_propagates_status_reason_and_no_blend_data():
    a = _prep(fx.decay_fixture(150.0, 0.02, n=24000))
    b = _prep(fx.silent())
    cfg = PairComparisonConfig()
    assert a.status == AnalysisStatus.OK
    assert b.status == AnalysisStatus.SILENT

    pair = compare_pair(a, b, cfg)
    blend = predict_blend(a, b, cfg, alignment='suggested')

    for result in (pair, blend):
        assert result.status == b.status
        assert result.status != AnalysisStatus.OK
        assert 'b' in result.reason.lower()
        assert b.status.value in result.reason.lower()

    assert pair.polarity == 0
    assert pair.phase_diff_weighted_rms_deg is None
    assert blend.freqs is None
    assert blend.magnitude_db is None
    assert blend.ratios == ()


# ---- blend prediction ---------------------------------------------------------------
def test_blend_prediction_matches_zero_delay_time_domain_sum():
    a = fx.boxy_fixture(250.0, 0.02, n=24000)
    b = fx.boxy_fixture(280.0, 0.03, n=24000)
    pa, pb = _prep(a), _prep(b)
    pred = predict_blend(pa, pb, PairComparisonConfig(), delay_samples=0.0,
                         polarity=1, alignment='raw')
    assert pred.status == AnalysisStatus.OK
    assert pred.verified_rms_db is not None
    assert pred.verified_rms_db <= 0.25, pred.verified_rms_db


def test_blend_prediction_matches_processed_crossfade_spectra():
    a = np.zeros(2048)
    b = np.zeros(2048)
    a[128:136] = (0.8, -0.35, 0.15, 0.05, -0.08, 0.02, 0.01, -0.01)
    b[128:136] = (-0.25, 0.6, 0.1, -0.3, 0.04, 0.03, -0.02, 0.01)
    pa, pb = _prep(a), _prep(b)
    cfg = PairComparisonConfig(blend_ratios=(0.0, 0.5, 1.0))
    pair = PairComparisonResult(
        key_a=pa.key, key_b=pb.key, cfg=cfg, status=AnalysisStatus.OK,
        delay_samples=0.0, polarity=1,
    )
    a_before = pa.data.copy()
    b_before = pb.data.copy()

    pred = predict_blend(pa, pb, cfg, alignment='raw')
    nfft = (len(pred.freqs) - 1) * 2
    for i, ratio_b in enumerate(pred.ratios):
        mix, sr, warnings = blend_sum(pa, pb, pair, ratio_b)
        actual_db = 20 * np.log10(np.maximum(
            np.abs(np.fft.rfft(mix[:, 0], nfft)), 1e-30))
        assert sr == pa.sample_rate
        assert warnings == []
        np.testing.assert_allclose(pred.magnitude_db[i], actual_db,
                                   rtol=0, atol=1e-10)

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)


def test_comb_cancellation_detected_for_inverted_blend():
    a = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    b = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)  # identical
    pa, pb = _prep(a), _prep(b)
    cfg = PairComparisonConfig(blend_ratios=(0.5,))
    pred = predict_blend(pa, pb, cfg, delay_samples=0.0, polarity=-1,
                         alignment='suggested')
    # A 50/50 crossfade of identical, opposite-polarity signals cancels.
    assert pred.worst_cancellation_db is not None
    assert pred.worst_cancellation_db > 24.0


def test_b04_cancellation_evidence_tracks_each_blend_ratio():
    signal = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    a, b = _prep(signal), _prep(-signal.copy())
    ratios = (0.0, 0.5, 1.0)
    pred = predict_blend(
        a, b, PairComparisonConfig(blend_ratios=ratios), alignment='raw',
    )

    assert pred.status == AnalysisStatus.OK
    assert pred.ratios == ratios
    losses = {ratio: _ratio_cancellation_loss(pred, ratio) for ratio in ratios}
    expected = {ratio: _inverse_polarity_loss_db(ratio) for ratio in ratios}

    assert expected[0.0] == expected[1.0] == 0.0
    assert expected[0.5] > 24.0
    assert abs(losses[0.0] - expected[0.0]) < 0.25
    assert losses[0.5] > 24.0
    assert abs(losses[1.0] - expected[1.0]) < 0.25


def test_constructive_blend_low_risk():
    a = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    pa, pb = _prep(a), _prep(a.copy())
    pred = predict_blend(pa, pb, PairComparisonConfig(blend_ratios=(0.5,)),
                         delay_samples=0.0, polarity=1, alignment='suggested')
    assert pred.worst_cancellation_db < 1.0
    assert pred.phase_compat_score is not None and pred.phase_compat_score > 0.9


def test_sensitivity_reports_both_offsets():
    a = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    b = fx.decay_fixture(150.0, 0.02, n=24000, delay_ms=2.0)
    pred = predict_blend(_prep(a), _prep(b), PairComparisonConfig(),
                         delay_samples=3.0, polarity=1, alignment='suggested')
    assert '-1' in pred.sensitivity and '+1' in pred.sensitivity
    assert pred.sensitivity['-1'] is not None and pred.sensitivity['+1'] is not None
