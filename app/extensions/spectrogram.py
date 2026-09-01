"""Spectrogram heatmap + band persistence metrics (WP-03).

Fixed local windows (unlike CSD's cumulative tails). Persistence scores turn
"the heatmap looks boxy" into numbers: persistent-band excess vs neighbor
bands, duration above threshold, dominant ridge frequency and Q.

B15: ``compare_spectrograms`` is the pure, shared-grid comparison helper used
by the A/B/Difference UI.  It resamples both sides onto one common log-freq /
linear-time grid (no ad-hoc interpolation inside Qt painting code), keeps an
explicit validity mask per side, and reports an explicit reason whenever the
pair cannot be compared.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
    # Stereo channel policy: keep every channel and power-aggregate the
    # per-channel spectra (mean of |FFT|^2) instead of a signed channel mean.
    data = prepared.data[prepared.onset:prepared.tail_end + 1]   # (n, ch)
    n_ch = data.shape[1]
    if len(data) < 256:
        return SpectrogramResult(key=prepared.key, cfg=cfg,
                                 status=AnalysisStatus.TOO_SHORT,
                                 warnings=('useful segment too short for '
                                           'spectrogram',))

    window_ms = cfg.window_ms()
    win = max(32, int(window_ms / 1000 * sr))
    win = min(win, len(data))
    hop = max(1, win // 4)
    nfft = next_pow2(win * 2)

    starts = list(range(0, max(1, len(data) - win // 2), hop))
    grid = log_freq_grid(cfg.fmin, cfg.fmax, cfg.points_per_octave)
    mat = np.empty((len(grid), len(starts)))
    window = np.hanning(win)
    for k, s in enumerate(starts):
        seg = data[s:s + win]
        if len(seg) < win:
            seg = np.pad(seg, ((0, win - len(seg)), (0, 0)))
        power = np.zeros(nfft // 2 + 1)
        for ch in range(n_ch):
            p, bins = fft_power_db(seg[:, ch] * window, sr, nfft)
            power += p
        power /= n_ch
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


# ---------------------------------------------------------------------------
# B15: shared-grid A/B comparison (pure; no Qt imports here)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpectrogramComparison:
    """Two spectrograms resampled onto one shared reference grid.

    ``magnitude_*_db`` are relative to the common ``ref_db`` (the louder peak
    of the two over the shared overlap), so A and B share an identical dB
    reference.  ``diff_db = magnitude_a_db - magnitude_b_db`` is therefore a
    physical dB difference and exactly negates when A and B are swapped.

    ``valid_a`` / ``valid_b`` / ``valid_diff`` are per-grid-point (n_freq,
    n_time) boolean masks combining the source reliability masks with
    finite-value checks after resampling.
    """
    available: bool
    reason: str = ''
    freqs: np.ndarray | None = None            # (n_freq,) shared log grid, Hz
    times_ms: np.ndarray | None = None         # (n_time,) shared linear grid
    magnitude_a_db: np.ndarray | None = None   # (n_freq, n_time) vs ref_db
    magnitude_b_db: np.ndarray | None = None
    valid_a: np.ndarray | None = None          # (n_freq, n_time) bool
    valid_b: np.ndarray | None = None
    diff_db: np.ndarray | None = None          # a - b (dB), common reference
    valid_diff: np.ndarray | None = None
    ref_db: float = 0.0                        # common dB reference for A/B
    overlap_time_ms: tuple = field(default_factory=tuple)
    overlap_freq_hz: tuple = field(default_factory=tuple)


def spectrogram_error(result) -> str | None:
    """Validate one spectrogram result; ``None`` when it is usable.

    Returns a human-readable reason (never an exception) when the result is
    missing, malformed, non-finite or carries an analysis failure status.
    """
    if result is None:
        return 'unavailable'
    if getattr(result, 'status', None) != AnalysisStatus.OK:
        value = getattr(getattr(result, 'status', None), 'value', None)
        return str(getattr(result, 'status', None)).replace('_', ' ') \
            if value is None else str(value).replace('_', ' ')
    if (getattr(result, 'magnitude_db', None) is None or
            getattr(result, 'freqs', None) is None or
            getattr(result, 'times_ms', None) is None):
        return 'missing spectrogram data'
    try:
        magnitude = np.asarray(result.magnitude_db, dtype=float)
        freqs = np.asarray(result.freqs, dtype=float)
        times = np.asarray(result.times_ms, dtype=float)
    except (TypeError, ValueError):
        return 'malformed spectrogram data'
    if magnitude.ndim != 2:
        return 'magnitude matrix is not two-dimensional'
    if freqs.ndim != 1 or not len(freqs):
        return 'frequency axis is missing or malformed'
    if times.ndim != 1 or not len(times):
        return 'time axis is missing or malformed'
    if magnitude.shape != (len(freqs), len(times)):
        return 'magnitude matrix does not match its axes'
    if (not np.all(np.isfinite(magnitude)) or
            not np.all(np.isfinite(freqs)) or not np.all(freqs > 0) or
            not np.all(np.isfinite(times))):
        return 'spectrogram data contains invalid values'
    if ((len(freqs) > 1 and np.any(np.diff(freqs) <= 0)) or
            (len(times) > 1 and np.any(np.diff(times) <= 0))):
        return 'spectrogram axes must increase'
    return None


def _effective_ppo(spec_a, spec_b, fallback: int = 24) -> int:
    """Shared log-frequency resolution: the denser of the two configs."""
    values = []
    for spec in (spec_a, spec_b):
        cfg = getattr(spec, 'cfg', None)
        v = getattr(cfg, 'points_per_octave', None)
        if isinstance(v, int) and v > 0:
            values.append(v)
    return max(values) if values else fallback


def _axis_step(times: np.ndarray, hop_ms: float) -> float:
    """Time step of one spectrogram: the documented hop, else the median
    frame spacing of the actual grid."""
    if hop_ms and hop_ms > 0:
        return float(hop_ms)
    d = np.diff(times)
    d = d[d > 0]
    return float(np.median(d)) if len(d) else 1.0


def _shared_freq_grid(fa: np.ndarray, fb: np.ndarray, ppo: int
                      ) -> np.ndarray | None:
    fmin = max(float(fa[0]), float(fb[0]))
    fmax = min(float(fa[-1]), float(fb[-1]))
    if not (fmax > fmin and fmin > 0):
        return None
    return log_freq_grid(fmin, fmax, ppo)


def _shared_time_grid(ta: np.ndarray, tb: np.ndarray, hop_a: float,
                      hop_b: float) -> np.ndarray | None:
    t0 = max(float(ta[0]), float(tb[0]))
    t1 = min(float(ta[-1]), float(tb[-1]))
    if not (t1 > t0):
        return None
    step = min(_axis_step(ta, hop_a), _axis_step(tb, hop_b))
    if not (step > 0):
        return None
    n = min(1024, max(2, int(round((t1 - t0) / step)) + 1))
    return np.linspace(t0, t1, n)


def _resample(mag: np.ndarray, src_freqs: np.ndarray, src_times: np.ndarray,
              dst_freqs: np.ndarray, dst_times: np.ndarray) -> np.ndarray:
    """Linear interpolation onto the shared grid.

    Frequencies are interpolated in log-frequency space (both grids are
    log-spaced), then time columns in linear ms.  All shared-grid points lie
    inside both source ranges (the grid is their intersection), so the
    interpolation is always in-range and never extrapolates.
    """
    x_src = np.log10(src_freqs)
    x_dst = np.log10(dst_freqs)
    tmp = np.column_stack([np.interp(x_dst, x_src, mag[:, t])
                           for t in range(mag.shape[1])])
    out = np.vstack([np.interp(dst_times, src_times, tmp[f, :])
                     for f in range(len(x_dst))])
    return out


def _resample_mask(src_mask: np.ndarray, src_freqs: np.ndarray,
                   dst_freqs: np.ndarray) -> np.ndarray:
    """Reliability mask pulled onto the shared grid (bool per freq point)."""
    if src_mask is None or len(src_mask) != len(src_freqs):
        return np.ones(len(dst_freqs), dtype=bool)
    return np.interp(np.log10(dst_freqs), np.log10(src_freqs),
                     src_mask.astype(np.float64)) > 0.5


def compare_spectrograms(spec_a, spec_b,
                         points_per_octave: int | None = None
                         ) -> SpectrogramComparison:
    """Resample A and B onto one shared log-freq / linear-time grid (B15).

    Returns an explicit ``reason`` whenever the pair cannot be compared
    (malformed input, empty frequency/time overlap, or no reliable bins in
    the overlap) instead of leaving the caller to guess.

    The result is symmetric under A/B swap: the shared grid, reference and
    validity masks are identical and ``diff_db`` exactly negates.
    """
    err_a = spectrogram_error(spec_a)
    if err_a is not None:
        return SpectrogramComparison(False,
                                     f'IR A spectrogram unavailable: {err_a}')
    err_b = spectrogram_error(spec_b)
    if err_b is not None:
        return SpectrogramComparison(False,
                                     f'IR B spectrogram unavailable: {err_b}')

    fa = np.asarray(spec_a.freqs, dtype=float)
    fb = np.asarray(spec_b.freqs, dtype=float)
    ta = np.asarray(spec_a.times_ms, dtype=float)
    tb = np.asarray(spec_b.times_ms, dtype=float)
    ppo = points_per_octave or _effective_ppo(spec_a, spec_b)

    freqs = _shared_freq_grid(fa, fb, ppo)
    if freqs is None:
        return SpectrogramComparison(False, (
            f'No overlapping frequency range (A {fa[0]:.0f}–{fa[-1]:.0f} Hz, '
            f'B {fb[0]:.0f}–{fb[-1]:.0f} Hz)'))
    times = _shared_time_grid(ta, tb, float(getattr(spec_a, 'hop_ms', 0.0)),
                              float(getattr(spec_b, 'hop_ms', 0.0)))
    if times is None:
        return SpectrogramComparison(False, (
            f'No overlapping time range (A {ta[0]:.1f}–{ta[-1]:.1f} ms, '
            f'B {tb[0]:.1f}–{tb[-1]:.1f} ms)'))
    if len(times) < 2:
        return SpectrogramComparison(
            False, 'Time overlap is too small for a comparison grid')

    ma = _resample(np.asarray(spec_a.magnitude_db, dtype=float),
                   fa, ta, freqs, times)
    mb = _resample(np.asarray(spec_b.magnitude_db, dtype=float),
                   fb, tb, freqs, times)

    freq_ok_a = _resample_mask(getattr(spec_a, 'valid_mask', None), fa, freqs)
    freq_ok_b = _resample_mask(getattr(spec_b, 'valid_mask', None), fb, freqs)
    valid_a = freq_ok_a[:, None] & np.isfinite(ma)
    valid_b = freq_ok_b[:, None] & np.isfinite(mb)
    valid_diff = valid_a & valid_b
    if not bool(valid_diff.any()):
        return SpectrogramComparison(
            False, 'No reliable bins in the overlapping region for comparison')

    ref_db = float(max(float(np.nanmax(ma)), float(np.nanmax(mb))))
    return SpectrogramComparison(
        True, '', freqs=freqs, times_ms=times,
        magnitude_a_db=ma - ref_db, magnitude_b_db=mb - ref_db,
        valid_a=valid_a, valid_b=valid_b, diff_db=ma - mb,
        valid_diff=valid_diff, ref_db=ref_db,
        overlap_time_ms=(float(times[0]), float(times[-1])),
        overlap_freq_hz=(float(freqs[0]), float(freqs[-1])))


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
