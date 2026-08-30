"""Non-destructive IR processing (WP-08).

Builds in-memory processed copies (alignment, polarity, optional peak
normalization, blend sums). Nothing here writes files or touches the source —
export lives in processing_export.py. Fractional delay is implemented as a
zero-padded frequency-domain phase ramp (linear, non-circular).
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, BlendPrediction, IRProcessingConfig,
                        PairComparisonResult, PreparedIR)
from .time_frequency import next_pow2


def fractional_shift(x: np.ndarray, advance_samples: float) -> np.ndarray:
    """Advance `x` by `advance_samples` (linear shift, zero-padded FFT).

    Works on (n,) or (n, ch) float arrays; output keeps the input shape.
    """
    n = len(x)
    if abs(advance_samples) < 1e-9:
        return x.copy()
    pad = next_pow2(n + int(abs(advance_samples)) + 8)
    xp = np.zeros_like(x, shape=(pad,) + x.shape[1:])
    xp[:n] = x
    X = np.fft.rfft(xp, axis=0)
    f = np.fft.rfftfreq(pad, 1.0)
    ramp = np.exp(2j * np.pi * f * advance_samples)
    if x.ndim > 1:
        ramp = ramp[:, None]
    ys = np.fft.irfft(X * ramp, pad, axis=0)[:n]
    return ys


def apply_alignment(prepared: PreparedIR, cfg: IRProcessingConfig
                    ) -> tuple[np.ndarray, list[str]]:
    """Return a processed COPY of the prepared IR (all channels treated
    identically) with the suggested delay/polarity applied."""
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        raise ValueError(f'cannot process IR with status {prepared.status.value}')
    warnings = list(prepared.warnings)
    x = np.array(prepared.data, dtype=np.float64, copy=True)
    if cfg.polarity == -1:
        x = -x
    if abs(cfg.delay_samples) >= 1e-9:
        x = fractional_shift(x, cfg.delay_samples)
    if cfg.normalize_peak_dbfs is not None:
        peak = float(np.max(np.abs(x)))
        if peak > 0:
            target = 10 ** (cfg.normalize_peak_dbfs / 20.0)
            x = x * (target / peak)
        else:
            warnings.append('silent IR: normalization skipped')
    return x, warnings


def blend_sum(a: PreparedIR, b: PreparedIR,
              pair: PairComparisonResult, ratio_b: float,
              cfg: IRProcessingConfig | None = None) -> tuple[np.ndarray, int, list[str]]:
    """Time-domain aligned sum gA*A + gB*s*B(advanced), per plan section 8.5.

    Uses the measured pair alignment. Returns (mix (n, ch), sr, warnings).
    """
    if a.status != AnalysisStatus.OK or b.status != AnalysisStatus.OK:
        raise ValueError('both IRs must analyze cleanly before blending')
    sr = a.sample_rate
    ch = max(a.channels, b.channels)
    advance = pair.delay_samples
    s = pair.polarity if pair.polarity != 0 else 1
    b_cfg = IRProcessingConfig(delay_samples=advance, polarity=s)
    xbc, _ = apply_alignment(b, b_cfg)

    n = max(a.frames, len(xbc)) + int(abs(advance)) + 8
    A = np.zeros((n, a.channels))
    A[:a.frames] = a.data
    B = np.zeros((n, b.channels))
    B[:len(xbc)] = xbc
    if B.shape[1] < ch:
        B = np.tile(B, (1, ch))[:, :ch]
    if A.shape[1] < ch:
        A = np.tile(A, (1, ch))[:, :ch]
    gA, gB = 1.0 - ratio_b, ratio_b
    mix = gA * A + gB * B
    warnings = []
    _ = cfg
    return mix, sr, warnings
