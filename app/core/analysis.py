"""Impulse-response spectral analysis: smoothed magnitude curve + tone metrics."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import median_filter

from .audio_io import load_ir

# Shared constants ----------------------------------------------------------
CURVE_FMIN = 20.0
CURVE_FMAX = 20000.0
N_CURVE = 96

# (name, low Hz, high Hz) — the 7 screening bands
BANDS: list[tuple[str, float, float]] = [
    ('Sub', 20.0, 60.0),
    ('Low', 60.0, 120.0),
    ('LowMid', 120.0, 350.0),
    ('Mid', 350.0, 1000.0),
    ('MidHigh', 1000.0, 3500.0),
    ('High', 3500.0, 8000.0),
    ('Air', 8000.0, 20000.0),
]
BAND_NAMES = [b[0] for b in BANDS]
BAND_CENTERS = np.array([(lo * hi) ** 0.5 for _, lo, hi in BANDS])

SCORE_LO = 80.0
SCORE_HI = 8000.0
FLATNESS_LO = 80.0
FLATNESS_HI = 8000.0
TILT_LO = 200.0
TILT_HI = 8000.0
N_WAVE = 400

CURVE_FREQS = np.geomspace(CURVE_FMIN, CURVE_FMAX, N_CURVE)


@dataclass
class AnalysisResult:
    path: str
    sample_rate: int
    channels: int
    n_samples: int
    length_ms: float
    effective_length_ms: float
    flatness_db: float
    tilt_db_oct: float
    band_levels: dict[str, float]   # dB relative to the curve's overall mean (0 dB)
    peak_freq: float
    peak_db: float
    notch_freq: float
    notch_db: float
    curve_db: np.ndarray            # (N_CURVE,) core-band-normalized magnitude
    wave: np.ndarray                # (N_WAVE,) 0..1 peak envelope for mini display
    tags: list[str] = field(default_factory=list)   # derived from metrics (+ library stats)
    score: float | None = None      # runtime-only ranking score, never cached


@dataclass
class LibraryStats:
    """Medians used to derive tone tags relative to the library itself."""
    tilt_db_oct: float
    low: float
    lowmid: float
    mid: float
    high: float
    air: float


def compute_library_stats(results: list[AnalysisResult]) -> LibraryStats | None:
    if len(results) < 20:
        return None
    med = np.median
    return LibraryStats(
        tilt_db_oct=med([r.tilt_db_oct for r in results]),
        low=med([r.band_levels['Low'] for r in results]),
        lowmid=med([r.band_levels['LowMid'] for r in results]),
        mid=med([r.band_levels['Mid'] for r in results]),
        high=med([r.band_levels['High'] for r in results]),
        air=med([r.band_levels['Air'] for r in results]),
    )


def derive_tags(result: AnalysisResult, stats: LibraryStats | None) -> list[str]:
    """Tone tags. With library stats they describe each IR relative to the
    library's own median character; without (small libraries) absolute rules apply."""
    t, b = result.tilt_db_oct, result.band_levels
    tags: list[str] = []
    if stats is None:
        if result.flatness_db <= 2.0:
            tags.append('Flat')
        if t >= 1.0 or b['High'] >= -1.0:
            tags.append('Bright')
        if t <= -1.0 or b['High'] <= -4.0:
            tags.append('Dark')
        if b['LowMid'] >= 2.0 and t <= 0.3:
            tags.append('Warm')
        if (b['Low'] + b['High']) / 2 - b['Mid'] >= 3.0:
            tags.append('Scooped')
        if b['Mid'] >= 2.0:
            tags.append('Mid-forward')
        if b['Low'] >= 3.0:
            tags.append('Boomy')
        if b['Low'] <= -3.0 and b['LowMid'] <= -1.5:
            tags.append('Thin')
        if b['Air'] >= 3.0 or (b['Air'] - b['High'] >= 6.0 and b['Air'] >= -6.0):
            tags.append('Fizzy')
        return tags

    if result.flatness_db <= 2.0:
        tags.append('Flat')
    if t >= stats.tilt_db_oct + 0.5:
        tags.append('Bright')
    if t <= stats.tilt_db_oct - 0.5:
        tags.append('Dark')
    if b['LowMid'] >= stats.lowmid + 1.0 and t <= stats.tilt_db_oct + 0.3:
        tags.append('Warm')
    if (b['Low'] + b['High']) / 2 - b['Mid'] >= 3.0:
        tags.append('Scooped')
    if b['Mid'] >= stats.mid + 1.0:
        tags.append('Mid-forward')
    if b['Low'] >= stats.low + 1.5:
        tags.append('Boomy')
    if b['Low'] <= stats.low - 1.5:
        tags.append('Thin')
    if b['Air'] >= stats.air + 2.0:
        tags.append('Fizzy')
    return tags


def _next_pow2(n: int) -> int:
    return 1 << (int(n) - 1).bit_length()


def _smoothed_power_db(data: np.ndarray, sr: int) -> np.ndarray:
    """1/6-octave smoothed power spectrum in dB, sampled at CURVE_FREQS.

    Multi-channel input is averaged in the power domain.
    """
    data = data - data.mean(axis=0, keepdims=True)
    nfft = _next_pow2(max(data.shape[0] * 2, 65536))
    bins = np.fft.rfftfreq(nfft, 1.0 / sr)
    power = np.zeros(len(bins))
    for ch in range(data.shape[1]):
        spec = np.fft.rfft(data[:, ch], nfft)
        power += spec.real ** 2 + spec.imag ** 2
    power /= data.shape[1]

    half = 2.0 ** (1.0 / 24.0)  # +/- 1/12 octave around each center -> ~1/6 oct wide
    lo = np.maximum(CURVE_FREQS / half, bins[1])
    hi = np.maximum(CURVE_FREQS * half, bins[1] * 2)
    i0 = np.searchsorted(bins, lo, side='left')
    i1 = np.searchsorted(bins, hi, side='right')
    out = np.empty(N_CURVE)
    for i, (a, b) in enumerate(zip(i0, i1)):
        a = min(a, len(power) - 1)
        b = max(b, a + 1)
        out[i] = 10.0 * np.log10(max(power[a:b].mean(), 1e-300))
    # Normalize on the core band (80 Hz - 8 kHz): guitar-cab curves are then
    # compared around a meaningful 0 dB, and top-end rolloff reads as negative.
    core = (CURVE_FREQS >= FLATNESS_LO) & (CURVE_FREQS <= FLATNESS_HI)
    out -= out[core].mean()
    return out


def _band_mean(curve: np.ndarray, lo: float, hi: float) -> float:
    mask = (CURVE_FREQS >= lo) & (CURVE_FREQS <= hi)
    return float(curve[mask].mean())


def _effective_bounds(data: np.ndarray, sr: int) -> tuple[int, int, float]:
    """Return (onset, end, effective_length_ms) using a -60 dB RMS tail threshold."""
    env = np.max(np.abs(data), axis=1)
    peak = float(env.max())
    if peak <= 0.0:
        return 0, len(env) - 1, 0.0
    onset = int(np.argmax(env > peak * 0.02))

    win = max(1, int(0.005 * sr))
    sq = data[:, 0] ** 2 if data.shape[1] == 1 else (data ** 2).mean(axis=1)
    cs = np.concatenate(([0.0], np.cumsum(sq)))
    n = len(sq)
    w0 = np.arange(0, n, win)
    w1 = np.minimum(w0 + win, n)
    rms = np.sqrt((cs[w1] - cs[w0]) / np.maximum(w1 - w0, 1))
    rms_peak = float(rms.max())
    above = np.nonzero(rms > rms_peak * 1e-3)[0]
    end = int(min(w1[above[-1]], n - 1)) if len(above) else n - 1
    return onset, end, max(0.0, (end - onset) / sr * 1000.0)


def _wave_envelope(data: np.ndarray, n_points: int = N_WAVE) -> np.ndarray:
    env = np.max(np.abs(data), axis=1)
    idx = np.linspace(0, len(env), n_points + 1).astype(int)
    out = np.empty(n_points)
    for i, (a, b) in enumerate(zip(idx[:-1], idx[1:])):
        out[i] = env[a:max(b, a + 1)].max()
    peak = out.max()
    return out / peak if peak > 0 else out


def analyze_data(data: np.ndarray, sr: int, path: str = '') -> AnalysisResult:
    """Analyze an in-memory IR shaped (n_samples,) or (n_samples, channels)."""
    if data.ndim == 1:
        data = data[:, None]
    n, ch = data.shape
    curve = _smoothed_power_db(data, sr)

    onset, end, eff_ms = _effective_bounds(data, sr)
    length_ms = n / sr * 1000.0

    flatness = float(np.abs(
        curve[(CURVE_FREQS >= FLATNESS_LO) & (CURVE_FREQS <= FLATNESS_HI)]
        - _band_mean(curve, FLATNESS_LO, FLATNESS_HI)
    ).mean())
    tilt_mask = (CURVE_FREQS >= TILT_LO) & (CURVE_FREQS <= TILT_HI)
    tilt = float(np.polyfit(np.log2(CURVE_FREQS[tilt_mask]), curve[tilt_mask], 1)[0])

    band_levels = {name: _band_mean(curve, lo, hi) for name, lo, hi in BANDS}

    residual = curve - median_filter(curve, size=9, mode='nearest')
    view = (CURVE_FREQS >= 100.0) & (CURVE_FREQS <= 12000.0)
    res_v = np.where(view, residual, -np.inf)
    ipk = int(np.argmax(res_v))
    res_n = np.where(view, residual, np.inf)
    int_ = int(np.argmin(res_n))

    result = AnalysisResult(
        path=path,
        sample_rate=sr,
        channels=ch,
        n_samples=n,
        length_ms=length_ms,
        effective_length_ms=eff_ms,
        flatness_db=flatness,
        tilt_db_oct=tilt,
        band_levels=band_levels,
        peak_freq=float(CURVE_FREQS[ipk]),
        peak_db=float(residual[ipk]),
        notch_freq=float(CURVE_FREQS[int_]),
        notch_db=float(residual[int_]),
        curve_db=curve,
        wave=_wave_envelope(data),
    )
    result.tags = derive_tags(result, None)
    return result


def analyze_file(path: str) -> AnalysisResult:
    data, sr = load_ir(path)
    return analyze_data(data, sr, path=str(path))
