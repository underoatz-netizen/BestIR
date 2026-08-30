"""Target-curve construction and IR ranking."""
from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator

from .analysis import BANDS, CURVE_FREQS, SCORE_LO, SCORE_HI, AnalysisResult


def target_from_band_offsets(offsets: dict[str, float]) -> np.ndarray:
    """Build a (N_CURVE,) target curve from {band_name: dB} offsets."""
    freqs = [(lo * hi) ** 0.5 for _, lo, hi in BANDS]
    values = [offsets.get(name, 0.0) for name, _, _ in BANDS]
    return target_from_points(freqs, values)


def target_from_points(freqs, values_db) -> np.ndarray:
    """Interpolate scattered (freq, dB) control points onto CURVE_FREQS (PCHIP on log-f)."""
    freqs = np.asarray(freqs, dtype=float)
    values_db = np.asarray(values_db, dtype=float)
    order = np.argsort(freqs)
    freqs, values_db = freqs[order], values_db[order]
    lx = np.log2(np.clip(freqs, 1.0, 1e6))
    pch = PchipInterpolator(lx, values_db, extrapolate=True)
    lq = np.log2(np.clip(CURVE_FREQS, freqs[0], freqs[-1]))
    return np.asarray(pch(lq), dtype=float)


def _mean_removed(curve: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (CURVE_FREQS >= lo) & (CURVE_FREQS <= hi)
    vals = curve[mask]
    return vals - vals.mean()


def score_curve(curve_db: np.ndarray, target_db: np.ndarray,
                lo: float = SCORE_LO, hi: float = SCORE_HI) -> float:
    """RMS distance (dB) between two mean-aligned curves over [lo, hi]."""
    a = _mean_removed(curve_db, lo, hi)
    b = _mean_removed(target_db, lo, hi)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def rank_records(records: list[AnalysisResult], target_db: np.ndarray,
                 lo: float = SCORE_LO, hi: float = SCORE_HI
                 ) -> list[AnalysisResult]:
    """Set .score on every record and return them sorted best-first."""
    for rec in records:
        rec.score = score_curve(rec.curve_db, target_db, lo, hi)
    return sorted(records, key=lambda r: (r.score is None, r.score, r.path))
