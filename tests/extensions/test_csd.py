"""WP-03 gates: CSD waterfall and spectrogram with persistence metrics."""
import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.adapters import LegacyIRAdapter
from app.extensions.cache import FingerprintCache
from app.extensions.contracts import (AnalysisStatus, AudioBuffer, SourceKey,
                                      PreprocessingConfig, TimeFrequencyConfig)
from app.extensions.csd import (DECAY_UNAVAILABLE_INSUFFICIENT,
                                DECAY_UNAVAILABLE_INVALID,
                                DECAY_UNAVAILABLE_NOISY,
                                DECAY_UNAVAILABLE_UNSUPPORTED,
                                compute_csd, decay_metric_key,
                                decay_validity)
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


# ---- B13: one metric-key contract, distinct unavailability states ----------
def test_b13_decay_metric_key_contract():
    assert decay_metric_key('40-120', 20.0) == 'D20_40-120_ms'
    assert decay_metric_key('40-120', 10.0) == 'D10_40-120_ms'
    assert decay_metric_key('1000-3500', 30.0) == 'D30_1000-3500_ms'
    # the validity key every consumer reads must be exactly '<key>_valid'
    # (fingerprint reads 'D20_40-120_ms_valid' — B13 mismatch regression)
    assert decay_metric_key('40-120', 20.0) + '_valid' == 'D20_40-120_ms_valid'


def test_b13_real_csd_metrics_carry_ms_valid_keys():
    res = compute_csd(_prep(fx.decay_fixture(80.0, 0.02, n=48000)),
                      TimeFrequencyConfig(profile='balanced'))
    for target in (10.0, 20.0, 30.0):
        key = decay_metric_key('40-120', target)
        assert key in res.metrics
        assert key + '_valid' in res.metrics
        assert res.metrics[key + '_valid'] is decay_validity(
            res.metrics, '40-120', target)[0]
    # bands the producer never measures are 'unsupported', never a silent False
    assert decay_validity(res.metrics, '120-350', 20.0) == (
        False, DECAY_UNAVAILABLE_UNSUPPORTED)


def test_b13_injected_valid_metric_reads_valid():
    metrics = {'D20_40-120_ms': 100.0, 'D20_40-120_ms_valid': True}
    assert decay_validity(metrics, '40-120', 20.0) == (True, 'valid')


def test_b13_unavailability_states_map_distinctly():
    key = decay_metric_key('40-120', 20.0)
    # unsupported: metric never produced for this band
    assert decay_validity({}, '40-120', 20.0) == (
        False, DECAY_UNAVAILABLE_UNSUPPORTED)
    # noisy: band bins fell below the reliability floor
    noisy = {key: None, key + '_valid': False, key + '_note': 'no valid band data'}
    assert decay_validity(noisy, '40-120', 20.0) == (
        False, DECAY_UNAVAILABLE_NOISY)
    # insufficient duration: gate too short to resolve the band edge
    short = {key: None, key + '_valid': False,
             key + '_note': 'gate 8 ms cannot resolve 40 Hz'}
    assert decay_validity(short, '40-120', 20.0) == (
        False, DECAY_UNAVAILABLE_INSUFFICIENT)
    # invalid: measured but the band never decayed to the target
    invalid = {key: None, key + '_valid': False,
               key + '_note': 'band never decayed to target in view'}
    assert decay_validity(invalid, '40-120', 20.0) == (
        False, DECAY_UNAVAILABLE_INVALID)
    states = {decay_validity(m, '40-120', 20.0)[1]
              for m in (noisy, short, invalid, {})}
    assert len(states) == 4


def test_b13_producer_notes_match_the_contract_states():
    # 30 ms window cannot resolve the 40 Hz band edge -> insufficient duration
    too_short = compute_csd(_prep(fx.decay_fixture(100.0, 0.01, n=1440)),
                            TimeFrequencyConfig(profile='balanced'))
    assert decay_validity(too_short.metrics, '40-120', 20.0)[1] == (
        DECAY_UNAVAILABLE_INSUFFICIENT)
    # resolvable gate but no 20 dB decay in view -> invalid
    undecayed = compute_csd(_prep(fx.decay_fixture(100.0, 0.01, n=2880)),
                            TimeFrequencyConfig(profile='low_end'))
    assert decay_validity(undecayed.metrics, '40-120', 20.0)[1] == (
        DECAY_UNAVAILABLE_INVALID)


def test_b13_csd_view_shows_injected_valid_and_distinct_states():
    """B13 gate: the view reads validity through the same accessor and tags
    noisy / insufficient / unsupported / invalid distinctly — no lumped
    'invalid/noisy' label."""
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.extensions.ui.csd_view import CsdView

    res = compute_csd(_prep(fx.decay_fixture(80.0, 0.02, n=48000)),
                      TimeFrequencyConfig(profile='balanced'))
    key = decay_metric_key('40-120', 20.0)

    def render(metrics):
        view = CsdView()
        try:
            fake = dataclasses.replace(res, metrics=metrics)
            view.show_csd(fake, 'A')
            return view._decay_text.toPlainText()
        finally:
            view.close()

    def band_line(text, band):
        return next(line for line in text.splitlines()
                    if line.startswith(f'• {band} Hz Band'))

    text = render({key: 100.0, key + '_valid': True})
    line = band_line(text, '40-120')
    assert '100 ms' in line and '✓' in line
    assert 'invalid/noisy' not in text
    # bands never measured for this source read 'unsupported' — shown separately
    assert '(not measured)' in band_line(text, '120-350')

    noisy = render({key: None, key + '_valid': False,
                    key + '_note': 'no valid band data'})
    assert '(noisy)' in band_line(noisy, '40-120')
    insufficient = render({key: None, key + '_valid': False,
                           key + '_note': 'gate 8 ms cannot resolve 40 Hz'})
    assert '(insufficient duration)' in band_line(insufficient, '40-120')
    invalid = render({key: None, key + '_valid': False,
                      key + '_note': 'band never decayed to target in view'})
    assert '(invalid)' in band_line(invalid, '40-120')
    # each state gets its own tag — none of them share a label
    assert '(noisy)' not in band_line(insufficient, '40-120')
    assert '(noisy)' not in band_line(invalid, '40-120')
    assert '(invalid)' not in band_line(noisy, '40-120')
    assert '✓' not in band_line(noisy, '40-120')
