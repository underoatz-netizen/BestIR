"""Spectrogram heatmap + band persistence metrics (WP-03).

Fixed local windows (unlike CSD's cumulative tails). Persistence scores turn
"the heatmap looks boxy" into numbers: persistent-band excess vs neighbor
bands, duration above threshold, dominant ridge frequency and Q.
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, PreparedIR, SpectrogramResult,
                        TimeFrequencyConfig)
from .time_frequency import (fft_power_db, log_freq_grid, next_pow2,
                             smooth_to_grid, to_db)

DEFAULT_PERSISTENCE_BAND = (180.0, 500.0)
DEFAULT_NEIGHBOR_BANDS = ((60.0, 180.0), (500.0, 2000.0))


def compute_spectrogram(prepared: PreparedIR, cfg: TimeFrequencyConfig,
                        persistence_band: tuple = DEFAULT_PERSISTENCE_BAND,
                        neighbor_bands: tuple = DEFAULT_NEIGHBOR_BANDS,
                        persistence_threshold_db: float = 6.0,
                        late_from_ms: float = 15.0) -> SpectrogramResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return SpectrogramResult(key=prepared.key, cfg=cfg,
                                 status=prepared.status,
                                 warnings=prepared.warnings)
    sr = prepared.sample_rate
    mono = prepared.data.mean(axis=1)[prepared.onset:prepared.tail_end + 1]
    if len(mono) < 256:
        return SpectrogramResult(key=prepared.key, cfg=cfg,
                                 status=AnalysisStatus.TOO_SHORT,
                                 warnings=('useful segment too short for '
                                           'spectrogram',))

    window_ms = cfg.window_ms()
    win = max(32, int(window_ms / 1000 * sr))
    win = min(win, len(mono))
    hop = max(1, win // 4)
    nfft = next_pow2(win * 2)

    starts = list(range(0, max(1, len(mono) - win // 2), hop))
    grid = log_freq_grid(cfg.fmin, cfg.fmax, cfg.points_per_octave)
    mat = np.empty((len(grid), len(starts)))
    window = np.hanning(win)
    for k, s in enumerate(starts):
        seg = mono[s:s + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        power, bins = fft_power_db(seg * window, sr, nfft)
        mat[:, k] = to_db(smooth_to_grid(power, bins, grid))

    peak_db = float(mat.max())
    mat = np.maximum(mat - peak_db, -cfg.dynamic_range_db)

    # reliability mask from the average spectrum
    avg_power = mat.mean(axis=1)
    valid_mask = avg_power >= (avg_power.max() + cfg.reliability_floor_db)

    times_ms = (np.array(starts, dtype=np.float64) + win / 2) / sr * 1000.0

    metrics, warnings = _persistence_metrics(
        mat, grid, times_ms, valid_mask, persistence_band, neighbor_bands,
        persistence_threshold_db, late_from_ms)
    return SpectrogramResult(key=prepared.key, cfg=cfg, status=AnalysisStatus.OK,
                             warnings=tuple(warnings), freqs=grid,
                             times_ms=times_ms, magnitude_db=mat,
                             valid_mask=valid_mask, window_ms=window_ms,
                             hop_ms=hop / sr * 1000.0, metrics=metrics)


def _persistence_metrics(mat: np.ndarray, grid: np.ndarray,
                         times_ms: np.ndarray, valid_mask: np.ndarray,
                         band: tuple, neighbors: tuple,
                         threshold_db: float, late_from_ms: float
                         ) -> tuple[dict, list]:
    metrics: dict = {}
    warnings: list = []
    lo, hi = band

    def band_curve(lo_hz: float, hi_hz: float) -> np.ndarray | None:
        m = (grid >= lo_hz) & (grid <= hi_hz) & valid_mask
        return mat[m].mean(axis=0) if m.any() else None

    target = band_curve(lo, hi)
    if target is None:
        return {'persistence_valid': False,
                'persistence_note': 'band has no valid bins'}, warnings

    neighbor_curves = [c for c in (band_curve(a, b) for a, b in neighbors)
                       if c is not None]
    if not neighbor_curves:
        return {'persistence_valid': False,
                'persistence_note': 'neighbor bands have no valid bins'}, warnings

    # persistence = the target band retains energy LATE relative to how fast
    # its neighbors fade (retention-based: immune to overall level differences)
    early = times_ms < late_from_ms
    late = times_ms >= late_from_ms
    if early.sum() < 1 or late.sum() < 1:
        return {'persistence_valid': False,
                'persistence_note': 'view too short for early/late windows'}, warnings

    def retention(curve: np.ndarray) -> float:
        """Negative dB drop from early to late (closer to 0 = more persistent)."""
        return float(curve[late].mean() - curve[early].mean())

    target_retention = retention(target)
    neighbor_retention = float(np.mean([retention(c) for c in neighbor_curves]))
    # positive when the target band decays SLOWER (more persistent) than neighbors
    excess = neighbor_retention - target_retention

    # duration the target band stays above (own peak - threshold)
    ref = float(target.max())
    above = np.nonzero(target >= ref - threshold_db)[0]
    duration_ms = (float(times_ms[above[-1]] - times_ms[above[0]])
                   if len(above) > 1 else 0.0)

    # dominant resonance in the band (time-averaged) and Q from -3 dB width
    avg = mat.mean(axis=1)
    in_band = (grid >= lo) & (grid <= hi)
    if in_band.any():
        seg_db = np.where(in_band, avg, -np.inf)
        ridge_i = int(np.argmax(seg_db))
        ridge_f = float(grid[ridge_i])
        ridge_level = float(avg[ridge_i])
        inside = in_band & (avg >= ridge_level - 3.0)
        width = grid[inside].max() - grid[inside].min() if inside.any() else np.nan
        q = ridge_f / width if width and width > 0 and np.isfinite(width) else None
    else:
        ridge_f, q = None, None

    metrics['persistence_band_hz'] = (lo, hi)
    metrics['persistence_excess_db'] = float(excess)
    metrics['persistence_duration_ms'] = duration_ms
    metrics['persistence_threshold_db'] = float(threshold_db)
    metrics['persistence_ridge_hz'] = ridge_f
    metrics['persistence_q'] = q
    metrics['persistence_valid'] = True
    metrics['persistence_note'] = ''
    if excess > threshold_db:
        metrics['persistence_flag'] = True
    else:
        metrics['persistence_flag'] = False
    return metrics, warnings
