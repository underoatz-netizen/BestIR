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

# ---- B13: single contract accessor for band-decay metrics ------------------
# Producer (_csd_metrics) and every consumer (CsdView, fingerprinting) must
# derive metric keys through `decay_metric_key` and read validity through
# `decay_validity`, so the key is `D20_<band>_ms_valid` everywhere.
DECAY_UNAVAILABLE_NOISY = 'noisy'
DECAY_UNAVAILABLE_INSUFFICIENT = 'insufficient duration'
DECAY_UNAVAILABLE_UNSUPPORTED = 'unsupported'
DECAY_UNAVAILABLE_INVALID = 'invalid'

_NOTE_NO_DATA = 'no valid band data'
_NOTE_NOT_DECAYED = 'band never decayed to target in view'


def decay_metric_key(band: str, target: float) -> str:
    """Canonical metric key, e.g. ('40-120', 20.0) -> 'D20_40-120_ms'."""
    return f'D{int(target)}_{band}_ms'


def decay_validity(metrics: dict, band: str,
                   target: float) -> tuple[bool, str]:
    """Return (valid, state) for one band-decay metric.

    `state` is 'valid' or one of the distinct unavailability reasons:
    'noisy' (band bins fell below the reliability floor),
    'insufficient duration' (gate too short to resolve the band edge),
    'unsupported' (metric not produced for this band),
    'invalid' (measured but unusable, e.g. no decay reached the target).
    """
    key = decay_metric_key(band, target)
    if key not in metrics:
        return False, DECAY_UNAVAILABLE_UNSUPPORTED
    if metrics.get(key + '_valid'):
        return True, 'valid'
    note = str(metrics.get(key + '_note') or '')
    if 'cannot resolve' in note:
        return False, DECAY_UNAVAILABLE_INSUFFICIENT
    if _NOTE_NO_DATA in note:
        return False, DECAY_UNAVAILABLE_NOISY
    return False, DECAY_UNAVAILABLE_INVALID


def compute_csd(prepared: PreparedIR, cfg: TimeFrequencyConfig,
                bands: tuple = DEFAULT_DECAY_BANDS) -> CSDResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return CSDResult(key=prepared.key, cfg=cfg, status=prepared.status,
                         warnings=prepared.warnings)
    sr = prepared.sample_rate
    onset, tail = prepared.onset, prepared.tail_end
    # Stereo channel policy: keep every channel; the transforms below
    # power-aggregate per-channel spectra (mean of |FFT|^2), never a signed
    # channel mean, so an anti-phase pair [x, -x] cannot cancel to silence.
    usable = prepared.data[onset:tail + 1]      # (n, ch)
    n_ch = usable.shape[1]
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
        # per-channel power spectra, power-aggregated across channels; for a
        # single channel this is exactly the legacy |FFT(seg*gate)|^2
        power = np.zeros(nfft // 2 + 1)
        for ch in range(n_ch):
            p, bins = fft_power_db(seg[:, ch] * gate, sr, nfft)
            power += p
        power /= n_ch
        smoothed = smooth_to_grid(power, bins, grid)
        mat[:, k] = to_db(smoothed)

    ref = mat[:, 0:1]
    csd_db = mat - ref
    csd_db = np.maximum(csd_db, -cfg.dynamic_range_db)

    # reliability mask from the reference transform (H_0)
    floor_lin = 10 ** (cfg.reliability_floor_db / 10.0)
    cap = min(len(usable), 8192)
    ref_cap = next_pow2(cap)
    ref_win = hann_edge_gate(cap)
    ref_power = np.zeros(ref_cap // 2 + 1)
    for ch in range(n_ch):
        p, _ = fft_power_db(usable[:cap, ch] * ref_win, sr, ref_cap)
        ref_power += p
    ref_power /= n_ch
    ref_smooth = smooth_to_grid(ref_power, np.fft.rfftfreq(
        ref_cap, 1.0 / sr), grid)
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
        name = decay_metric_key(low_key, target)
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
            metrics[f'{name}_note'] = _NOTE_NO_DATA
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
            metrics[f'{name}_note'] = _NOTE_NOT_DECAYED

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
