"""Non-destructive IR processing (WP-08).

Builds in-memory processed copies (alignment, polarity, optional peak
normalization, blend sums). Nothing here writes files or touches the source —
export lives in processing_export.py. Fractional delay is implemented as a
zero-padded frequency-domain phase ramp (linear, non-circular).
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, IRProcessingConfig, PairComparisonResult,
                        PreparedIR)
from .pair_preparation import prepare_pair
from .time_frequency import next_pow2


def fractional_shift(x: np.ndarray, advance_samples: float,
                     output_frames: int | None = None) -> np.ndarray:
    """Advance `x` by `advance_samples` (linear shift, zero-padded FFT).

    Works on (n,) or (n, ch) float arrays.  By default output keeps the input
    shape; ``output_frames`` retains delayed tails for pair blending.
    """
    n = len(x)
    out_n = n if output_frames is None else max(n, int(output_frames))
    if abs(advance_samples) < 1e-9:
        out = np.zeros((out_n,) + x.shape[1:], dtype=x.dtype)
        out[:n] = x
        return out
    pad = next_pow2(out_n + int(np.ceil(abs(advance_samples))) + 8)
    xp = np.zeros_like(x, shape=(pad,) + x.shape[1:])
    xp[:n] = x
    X = np.fft.rfft(xp, axis=0)
    f = np.fft.rfftfreq(pad, 1.0)
    ramp = np.exp(2j * np.pi * f * advance_samples)
    if x.ndim > 1:
        ramp = ramp[:, None]
    ys = np.fft.irfft(X * ramp, pad, axis=0)[:out_n]
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


def blend_gains(ratio_b: float) -> tuple[float, float]:
    """Return the documented linear crossfade gains for A and B."""
    return 1.0 - ratio_b, ratio_b


def blend_sum(a: PreparedIR, b: PreparedIR,
              pair: PairComparisonResult, ratio_b: float,
              cfg: IRProcessingConfig | None = None) -> tuple[np.ndarray, int, list[str]]:
    """Time-domain aligned sum gA*A + gB*s*B(advanced), per plan section 8.5.

    Uses the measured pair alignment. Returns (mix (n, ch), sr, warnings).
    """
    prepared = prepare_pair(a, b)
    if prepared.status != AnalysisStatus.OK:
        raise ValueError(prepared.reason or 'both IRs must analyze cleanly before blending')
    sr = prepared.sample_rate
    advance = float(pair.delay_samples)
    s = pair.polarity if pair.polarity != 0 else 1
    n = max(len(prepared.data_a), len(prepared.data_b)) + \
        int(np.ceil(abs(advance))) + 8
    A = np.zeros((n, prepared.data_a.shape[1]))
    A[:len(prepared.data_a)] = prepared.data_a
    B = fractional_shift(prepared.data_b, advance, output_frames=n)
    gA, gB = blend_gains(ratio_b)
    mix = gA * A + gB * s * B
    warnings = list(prepared.warnings)
    _ = cfg
    return mix, sr, warnings
