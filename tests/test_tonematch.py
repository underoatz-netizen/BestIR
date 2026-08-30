import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.analysis import (CURVE_FREQS, SCORE_HI, SCORE_LO, analyze_data,
                               analyze_file)
from app.core.matching import rank_records
from app.core.presets import PRESETS
from app.core.tonematch import (align_curve, curve_metrics, make_di_tone,
                                needed_ir_curve, output_curve)
from app.core.matching import target_from_band_offsets, target_from_points
from tests.synth import synth_ir, write_wav

ANCHORS = [20, 60, 120, 350, 1000, 3500, 8000, 20000]


def _curve(anchors):
    return target_from_points(ANCHORS, anchors)


def test_needed_curve_is_complement_of_di():
    di = _curve([0, -1, -2, -3, -5, -7, -9, -12])   # dark DI
    flat_out = target_from_band_offsets(PRESETS['Flat'])
    needed = needed_ir_curve(di, flat_out, SCORE_LO, SCORE_HI)
    # DI rolls off -> the IR must lift the top end
    low = needed[(CURVE_FREQS > 80) & (CURVE_FREQS < 200)].mean()
    high = needed[(CURVE_FREQS > 5000) & (CURVE_FREQS < 8000)].mean()
    assert high - low > 5.0


def test_output_curve_equals_convolution_spectrum(tmp_path):
    """DI_curve + IR_curve (dB domain) must equal the true convolved spectrum."""
    sr, n = 48000, 48000
    di_sig = synth_ir(sr=sr, n=n, anchors_db=[0, -1, -2, -4, -6, -8, -10, -14],
                      delay_ms=2.0, seed=1)
    ir_sig = synth_ir(sr=sr, n=9600, anchors_db=[0, 1, 2, 0, -2, -4, -6, -8],
                      delay_ms=1.0, seed=2)
    di_res = analyze_data(di_sig, sr)
    ir_path = write_wav(tmp_path / 'ir.wav', ir_sig, sr)
    ir_res = analyze_file(ir_path)

    predicted = output_curve(di_res.curve_db, ir_res.curve_db)
    actual = analyze_data(fftconvolve(di_sig, ir_sig)[:, None], sr).curve_db
    mask = (CURVE_FREQS >= SCORE_LO) & (CURVE_FREQS <= SCORE_HI)
    rms = float(np.sqrt(np.mean((predicted[mask] - actual[mask]) ** 2)))
    assert rms < 0.5, f'additive prediction off by {rms:.2f} dB RMS'


def test_rank_by_tone_match_prefers_complementing_ir():
    """Dark DI + 'balanced output' target -> brightest IR should win."""
    di = _curve([0, -1, -2, -3, -5, -7, -9, -12])
    bright = _curve([0, -1, -2, -1, 1, 3, 5, 3])
    dark = _curve([0, 1, 2, 1, -1, -3, -5, -4])
    needed = needed_ir_curve(di, target_from_band_offsets(PRESETS['Flat']),
                             SCORE_LO, SCORE_HI)

    class Rec:
        def __init__(self, name, curve):
            self.path = name
            self.curve_db = curve
            self.score = None

    ranked = rank_records([Rec('bright.wav', bright), Rec('dark.wav', dark)],
                          needed, SCORE_LO, SCORE_HI)
    assert ranked[0].path == 'bright.wav'


def test_make_di_tone_rejects_silence():
    try:
        make_di_tone(np.zeros(48000), 48000, 'silent')
        raise AssertionError('should have raised')
    except ValueError as exc:
        assert 'silent' in str(exc).lower()


def test_curve_metrics_matches_analysis():
    ir = synth_ir(anchors_db=[0, 1, 0, -1, 0, 1, 0, -1])
    res = analyze_data(ir, 48000)
    m = curve_metrics(res.curve_db)
    assert abs(m['flatness_db'] - res.flatness_db) < 1e-9
    assert abs(m['tilt_db_oct'] - res.tilt_db_oct) < 1e-9
    for band, v in res.band_levels.items():
        assert abs(m['band_levels'][band] - v) < 1e-9
