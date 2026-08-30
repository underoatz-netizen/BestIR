import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.analysis import CURVE_FREQS, N_CURVE
from app.core.matching import (rank_records, score_curve,
                               target_from_band_offsets, target_from_points)
from app.core.presets import PRESETS


def _curve_from_anchors(anchors_db, anchor_freqs=None):
    if anchor_freqs is None:
        anchor_freqs = [20, 60, 120, 350, 1000, 3500, 8000, 20000]
    return target_from_points(anchor_freqs, anchors_db)


def test_flat_preset_target_is_zero():
    t = target_from_band_offsets(PRESETS['Flat'])
    assert t.shape == (N_CURVE,)
    assert np.max(np.abs(t)) < 1.0  # interpolation ripple only at the extremes


def test_bright_target_tilts_up():
    t = target_from_band_offsets(PRESETS['Bright'])
    low = t[(CURVE_FREQS > 80) & (CURVE_FREQS < 120)].mean()
    high = t[(CURVE_FREQS > 8000) & (CURVE_FREQS < 12000)].mean()
    assert high - low > 3.0


def test_score_prefers_matching_curve():
    bright = _curve_from_anchors([-4, -2, -1, 0, 1, 2, 4, 2])
    dark = _curve_from_anchors([4, 2, 1, 0, -1, -2, -4, -3])
    target = target_from_band_offsets(PRESETS['Bright'])
    assert score_curve(bright, target) < score_curve(dark, target)


def test_rank_records_orders_best_first():
    bright = _curve_from_anchors([-4, -2, -1, 0, 1, 2, 4, 2])
    dark = _curve_from_anchors([4, 2, 1, 0, -1, -2, -4, -3])
    target = target_from_band_offsets(PRESETS['Dark'])

    class Rec:
        def __init__(self, name, curve):
            self.path = name
            self.curve_db = curve
            self.score = None

    recs = [Rec('bright.wav', bright), Rec('dark.wav', dark)]
    ranked = rank_records(recs, target)
    assert ranked[0].path == 'dark.wav'
    assert ranked[1].path == 'bright.wav'
    assert ranked[0].score < ranked[1].score


def test_drawn_points_interpolation():
    t = target_from_points([100, 1000, 10000], [0, -6, 3])
    i1k = int(np.argmin(np.abs(CURVE_FREQS - 1000)))
    assert abs(t[i1k] - (-6)) < 1.5
    assert t[0] >= 0 and t[-1] <= 3 + 0.5  # clamped to end anchors
