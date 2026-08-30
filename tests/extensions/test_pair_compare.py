"""WP-04 gates: phase, group delay, pair alignment, blend prediction."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AnalysisStatus, PairComparisonConfig,
                                      PhaseConfig)
from app.extensions.pair_compare import compare_pair, predict_blend
from app.extensions.phase import compute_phase
from app.extensions.preprocessing import prepare
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


# ---- phase ---------------------------------------------------------------------
def test_pure_delay_group_delay_matches_injected_delay():
    # delayed dirac: after onset alignment the impulse sits 1 ms after time
    # zero (the kept 1 ms pre-onset) -> group delay ~1 ms
    x = fx.dirac(delay_s=0.005)
    res = compute_phase(_prep(x), PhaseConfig())
    assert res.status == AnalysisStatus.OK
    gd = res.group_delay_ms[:, 0][res.valid_mask]
    assert 0.6 < np.nanmedian(gd) < 1.4, np.nanmedian(gd)
    assert res.coverage > 0.0


def test_unreliable_bins_masked_not_interpolated():
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    res = compute_phase(_prep(x), PhaseConfig(rel_threshold_db=-40.0))
    nan_bins = np.isnan(res.phase_rad[:, 0])
    assert nan_bins.sum() > 0
    assert np.all(np.isnan(res.phase_rad[nan_bins, 0]))
    valid_now = ~nan_bins
    assert np.all(res.valid_mask[valid_now])


def test_min_and_excess_phase_sum_to_total():
    x = fx.lowpassed_click(1500, n=24000)
    res = compute_phase(_prep(x), PhaseConfig(min_phase=True))
    ok = res.valid_mask & np.isfinite(res.min_phase_rad[:, 0]) \
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


# ---- blend prediction ---------------------------------------------------------------
def test_blend_prediction_matches_time_domain_sum():
    a = fx.boxy_fixture(250.0, 0.02, n=24000)
    b = fx.boxy_fixture(280.0, 0.03, n=24000)
    pa, pb = _prep(a), _prep(b)
    pred = predict_blend(pa, pb, PairComparisonConfig())
    assert pred.status == AnalysisStatus.OK
    assert pred.verified_rms_db is not None
    assert pred.verified_rms_db <= 0.25, pred.verified_rms_db


def test_comb_cancellation_detected_for_inverted_blend():
    a = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    b = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)  # identical
    pa, pb = _prep(a), _prep(b)
    cfg = PairComparisonConfig(blend_ratios=(1.0,))
    pred = predict_blend(pa, pb, cfg, delay_samples=0.0, polarity=-1,
                         alignment='suggested')
    # identical signals, opposite polarity, aligned -> total cancellation
    assert pred.worst_cancellation_db is not None
    assert pred.worst_cancellation_db > 24.0


def test_constructive_blend_low_risk():
    a = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    pa, pb = _prep(a), _prep(a.copy())
    pred = predict_blend(pa, pb, PairComparisonConfig(blend_ratios=(1.0,)),
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
