"""Cumulative Spectral Decay (WP-03).

CSD uses progressively later tail-gated transforms:

    H_k(f) = FFT{ h(t) * gate(t; start=t_k, end=tail) }
    CSD(f, t_k) = 20 log10(|H_k(f)| / |H_0(f)|)

Low-end claims are suppressed when the gate window cannot resolve them (at
20 Hz one cycle is 50 ms; a short gate cannot justify low-frequency detail).
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, CSDResult, PreparedIR,
                        TimeFrequencyConfig)
from .time_frequency import (fft_power_db, hann_edge_gate, log_freq_grid,
                             next_pow2, profile_gate_params, smooth_to_grid,
                             to_db)

DEFAULT_DECAY_BANDS = ((40.0, 120.0), (120.0, 350.0), (350.0, 1000.0),
                       (1000.0, 3500.0), (3500.0, 8000.0))


def compute_csd(prepared: PreparedIR, cfg: TimeFrequencyConfig,
                bands: tuple = DEFAULT_DECAY_BANDS) -> CSDResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return CSDResult(key=prepared.key, cfg=cfg, status=prepared.status,
                         warnings=prepared.warnings)
    sr = prepared.sample_rate
    mono = prepared.data.mean(axis=1)
    onset, tail = prepared.onset, prepared.tail_end
    usable = mono[onset:tail + 1]
    if len(usable) < 64:
        return CSDResult(key=prepared.key, cfg=cfg, status=AnalysisStatus.TOO_SHORT,
                         warnings=('useful segment too short for CSD',))

    hop_ms, min_gate_ms = profile_gate_params(cfg.profile)
    hop = max(1, int(hop_ms / 1000 * sr))
    min_gate = max(64, int(min_gate_ms / 1000 * sr))
    total = len(usable)

    gate_starts = list(range(0, max(1, total - 64), hop))
    # keep gates that still have at least min_gate samples of tail (except we
    # always keep the first gate = full useful window)
    gate_starts = [g for g in gate_starts if total - g >= min_gate] or [0]

    grid = log_freq_grid(cfg.fmin, cfg.fmax, cfg.points_per_octave)
    max_gate = max(total - g for g in gate_starts)
    nfft = next_pow2(max(2 * max_gate, 4096))

    mat = np.empty((len(grid), len(gate_starts)))
    for k, g0 in enumerate(gate_starts):
        seg = usable[g0:]
        gate = hann_edge_gate(len(seg))
        power, bins = fft_power_db(seg * gate, sr, nfft)
        smoothed = smooth_to_grid(power, bins, grid)
        mat[:, k] = to_db(smoothed)

    ref = mat[:, 0:1]
    csd_db = mat - ref
    csd_db = np.maximum(csd_db, -cfg.dynamic_range_db)

    # reliability mask from the reference transform (H_0)
    floor_lin = 10 ** (cfg.reliability_floor_db / 10.0)
    ref_power0, _ = fft_power_db(usable[:min(len(usable), 8192)] *
                                 hann_edge_gate(min(len(usable), 8192)),
                                 sr, next_pow2(min(len(usable), 8192)))
    ref_smooth = smooth_to_grid(ref_power0, np.fft.rfftfreq(
        next_pow2(min(len(usable), 8192)), 1.0 / sr), grid)
    ref_db = to_db(ref_smooth)
    valid_mask = ref_db >= (ref_db.max() + cfg.reliability_floor_db)

    times_ms = np.array(gate_starts, dtype=np.float64) / sr * 1000.0
    gate_ms = np.array([total - g for g in gate_starts], dtype=np.float64) / sr * 1000.0

    # band decay curves (energy averaged across the band's grid bins)
    band_decay = {}
    for lo, hi in bands:
        m = (grid >= lo) & (grid <= hi) & valid_mask
        band_decay[f'{lo:.0f}-{hi:.0f}'] = (
            mat[m].mean(axis=0) if m.any() else np.full(len(gate_starts), np.nan))

    metrics, warnings = _csd_metrics(band_decay, grid, valid_mask, mat,
                                     times_ms, float(gate_ms.max()) if
                                     len(gate_ms) else min_gate_ms, bands)
    return CSDResult(key=prepared.key, cfg=cfg, status=AnalysisStatus.OK,
                     warnings=tuple(warnings), freqs=grid, times_ms=times_ms,
                     magnitude_db=csd_db, valid_mask=valid_mask,
                     gate_window_ms=gate_ms, band_decay=band_decay,
                     metrics=metrics)


def _csd_metrics(band_decay: dict, grid: np.ndarray, valid_mask: np.ndarray,
                 mat: np.ndarray, times_ms: np.ndarray, min_gate_ms: float,
                 bands: tuple) -> tuple[dict, list]:
    """Decay-to-threshold times, slopes, and low-end late/early ratio."""
    warnings = []
    metrics: dict = {}
    low_key = None
    for name in band_decay:
        lo = float(name.split('-')[0])
        if lo <= 120:
            low_key = name
            break
    if low_key is None:
        low_key = next(iter(band_decay))

    curve = np.asarray(band_decay[low_key], dtype=float)
    finite = np.isfinite(curve)
    for target in (10.0, 20.0, 30.0):
        name = f'D{int(target)}_{low_key}_ms'
        # low-end validity: the reference gate must be long enough to resolve
        # roughly the lowest band edge (>= 2 cycles)
        lo_hz = float(low_key.split('-')[0])
        if min_gate_ms < 2.0 / max(lo_hz, 1e-6) * 1000.0:
            metrics[name] = None
            metrics[f'{name}_valid'] = False
            metrics[f'{name}_note'] = (
                f'gate {min_gate_ms:.0f} ms cannot resolve {lo_hz:.0f} Hz')
            continue
        if not finite.any():
            metrics[name] = None
            metrics[f'{name}_valid'] = False
            metrics[f'{name}_note'] = 'no valid band data'
            continue
        ref_val = float(curve[finite][0]) if finite[0] else float(curve[finite].max())
        dropped = ref_val - curve
        hit = np.nonzero(finite & (dropped >= target))[0]
        if len(hit):
            metrics[name] = float(times_ms[hit[0]])
            metrics[f'{name}_valid'] = True
            metrics[f'{name}_note'] = ''
        else:
            metrics[name] = None
            metrics[f'{name}_valid'] = False
            metrics[f'{name}_note'] = 'band never decayed to target in view'

    # decay slope over the -5..-25 dB region with fit confidence (R^2)
    ref_val = float(curve[np.isfinite(curve)][0]) if np.isfinite(curve).any() else 0.0
    dropped = ref_val - np.nan_to_num(curve, nan=np.inf)
    zone = np.isfinite(curve) & (dropped >= 5.0) & (dropped <= 25.0)
    if zone.sum() >= 4:
        t = times_ms[zone] / 1000.0
        y = curve[zone]
        slope, intercept = np.polyfit(t, y, 1)
        pred = slope * t + intercept
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        metrics[f'slope_{low_key}_db_per_s'] = float(slope)
        metrics[f'slope_{low_key}_r2'] = r2
    else:
        metrics[f'slope_{low_key}_db_per_s'] = None
        metrics[f'slope_{low_key}_r2'] = None
        metrics[f'slope_{low_key}_note'] = 'not enough decay in view'

    # low-frequency late/early energy ratio
    if len(times_ms) >= 4:
        q = max(1, len(times_ms) // 4)
        early = mat[low_band_mask(grid), :q][valid_mask[low_band_mask(grid)]].mean() \
            if valid_mask[low_band_mask(grid)].any() else np.nan
        late = mat[low_band_mask(grid), -q:][valid_mask[low_band_mask(grid)]].mean() \
            if valid_mask[low_band_mask(grid)].any() else np.nan
        metrics['low_late_early_ratio_db'] = (
            float(late - early) if np.isfinite(early) and np.isfinite(late) else None)
    else:
        metrics['low_late_early_ratio_db'] = None
    return metrics, warnings


def low_band_mask(grid: np.ndarray) -> np.ndarray:
    return (grid >= 40.0) & (grid <= 250.0)
