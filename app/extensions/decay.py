"""Decay metrics and guarded Schroeder T-derivations (WP-05).

Low-end band decay from CSD band energy is the primary cabinet-IR metric.
Formal Schroeder EDT/T20/T30 are reported only when the fixture actually
supports a reverberation measurement; short/noisy cabinet IRs get an explicit
invalid status instead of a fabricated T60.
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, DecayConfig, DecayResult, PreparedIR)
from .csd import DEFAULT_DECAY_BANDS, compute_csd
from .contracts import TimeFrequencyConfig


def compute_decay(prepared: PreparedIR, cfg: DecayConfig,
                  tf_cfg: TimeFrequencyConfig | None = None) -> DecayResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return DecayResult(key=prepared.key, cfg=cfg, status=prepared.status,
                           warnings=prepared.warnings)
    tf = tf_cfg or TimeFrequencyConfig(profile='balanced')
    csd = compute_csd(prepared, tf, bands=cfg.bands)
    if csd.status != AnalysisStatus.OK:
        return DecayResult(key=prepared.key, cfg=cfg, status=csd.status,
                           warnings=csd.warnings)

    band_decay_ms: dict = {}
    for name, curve in csd.band_decay.items():
        curve = np.asarray(curve, dtype=float)
        times = csd.times_ms
        finite = np.isfinite(curve)
        if not finite.any():
            band_decay_ms[name] = {'D10': None, 'D20': None, 'D30': None}
            continue
        ref = float(curve[finite][0])
        dropped = ref - curve
        for target in cfg.decay_targets_db:
            key = f'D{int(target)}'
            hit = np.nonzero(finite & (dropped >= target))[0]
            band_decay_ms.setdefault(name, {})[key] = (
                float(times[hit[0]]) if len(hit) else None)

    t20, t30, t60_est, t60_valid, reason = _schroeder_t(prepared, cfg)
    return DecayResult(key=prepared.key, cfg=cfg, status=AnalysisStatus.OK,
                       warnings=csd.warnings, band_decay_ms=band_decay_ms,
                       t20_ms=t20, t30_ms=t30, t60_estimate_ms=t60_est,
                       t60_valid=t60_valid, t60_reason=reason)


def _schroeder_t(prepared: PreparedIR, cfg: DecayConfig):
    """Schroeder backward-integration T20/T30 with strict validity.

    T60 is the -5..-35 dB linear fit extrapolated to -60 dB (more stable than
    fitting the noise-dominated tail directly).
    """
    sr = prepared.sample_rate
    mono = prepared.data.mean(axis=1)[prepared.onset:prepared.tail_end + 1]
    energy = np.cumsum((mono ** 2)[::-1])[::-1]
    total = float(energy[0]) if len(energy) else 0.0
    if total <= 0:
        return None, None, None, False, 'silent'
    db = 10.0 * np.log10(np.maximum(energy / total, 1e-30))

    def fit(t_hi_db: float, t_lo_db: float):
        hi = np.nonzero(db <= t_hi_db)[0]
        lo = np.nonzero(db <= t_lo_db)[0]
        if len(hi) == 0 or len(lo) == 0:
            return None
        i0, i1 = int(hi[0]), int(lo[-1])
        if i1 - i0 < sr * 0.05:     # need at least 50 ms of fit
            return None
        t = np.arange(i0, i1 + 1) / sr
        y = db[i0:i1 + 1]
        slope, intercept = np.polyfit(t, y, 1)
        if slope >= 0:
            return None
        pred = slope * t + intercept
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        if r2 < 0.95:
            return None
        return slope, intercept

    usable_range = float(-db[-1])   # total decay available in the window
    if usable_range < cfg.min_range_db:
        return None, None, None, False, (
            f'truncated / noise dominated: only {usable_range:.1f} dB of decay '
            'in the useful window; not a valid reverberation measurement')

    t20 = t30 = t60 = None
    fit30 = fit(-5.0, -35.0)
    if fit30 is not None:
        slope, intercept = fit30
        t30 = float((-35.0 - intercept) / slope) * 1000.0
        if usable_range >= 60.0:
            t60 = float((-60.0 - intercept) / slope) * 1000.0
    fit20 = fit(-5.0, -25.0)
    if fit20 is not None:
        t20 = float((-25.0 - fit20[0]) / fit20[1]) * 1000.0
    t60_valid = bool(t60 is not None and usable_range >= 45.0)
    reason = '' if t60_valid else (
        'not a valid reverberation measurement: cabinet-style IR lacks the '
        'dynamic range for T60')
    return t20, t30, t60, t60_valid, reason
