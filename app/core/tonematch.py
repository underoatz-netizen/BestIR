"""Tone-match workflow: DI as tone reference, needed-IR curve, output EQ.

Magnitude of a convolution is the sum of magnitudes (in dB), so the output EQ
of DI -> IR is exactly DI_curve + IR_curve up to a constant — no convolution
needed for analysis; convolution is only used for playback.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .analysis import (AnalysisResult, CURVE_FREQS, FLATNESS_HI, FLATNESS_LO,
                       analyze_data)


@dataclass
class DITone:
    """A dry guitar recording used as the tone reference of the chain."""
    name: str
    data: np.ndarray          # mono float64
    sr: int
    result: AnalysisResult    # spectral profile of the DI itself


def align_curve(curve: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Copy of the curve mean-removed over [lo, hi]."""
    mask = (CURVE_FREQS >= lo) & (CURVE_FREQS <= hi)
    return curve - curve[mask].mean()


def needed_ir_curve(di_curve: np.ndarray, target_output_curve: np.ndarray,
                    lo: float, hi: float) -> np.ndarray:
    """The IR magnitude curve that maps DI -> target output.

    N(f) = T(f) - D(f), both mean-aligned over the scoring range; the constant
    offset is irrelevant because scoring mean-aligns both sides anyway.
    """
    return (align_curve(target_output_curve, lo, hi)
            - align_curve(di_curve, lo, hi))


def output_curve(di_curve: np.ndarray, ir_curve: np.ndarray) -> np.ndarray:
    """Predicted chain output EQ (core-band normalized), = DI + IR."""
    out = di_curve + ir_curve
    mask = (CURVE_FREQS >= FLATNESS_LO) & (CURVE_FREQS <= FLATNESS_HI)
    return out - out[mask].mean()


def curve_metrics(curve: np.ndarray) -> dict:
    """Flatness / tilt / band levels of an arbitrary normalized curve."""
    mask = (CURVE_FREQS >= FLATNESS_LO) & (CURVE_FREQS <= FLATNESS_HI)
    vals = curve[mask]
    flatness = float(np.abs(vals - vals.mean()).mean())
    from .analysis import BANDS, TILT_HI, TILT_LO, _band_mean
    tilt_mask = (CURVE_FREQS >= TILT_LO) & (CURVE_FREQS <= TILT_HI)
    tilt = float(np.polyfit(np.log2(CURVE_FREQS[tilt_mask]),
                            curve[tilt_mask], 1)[0])
    bands = {name: _band_mean(curve, lo, hi) for name, lo, hi in BANDS}
    return {'flatness_db': flatness, 'tilt_db_oct': tilt, 'band_levels': bands}


def make_di_tone(data: np.ndarray, sr: int, name: str) -> DITone:
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    if peak <= 0.0:
        raise ValueError('The recording is silent — check the input device.')
    result = analyze_data(data[:, None], sr, path=name)
    return DITone(name=name, data=data, sr=sr, result=result)
