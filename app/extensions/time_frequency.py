"""Shared time-frequency utilities (WP-03)."""
from __future__ import annotations

import numpy as np


def log_freq_grid(fmin: float, fmax: float, points_per_octave: int) -> np.ndarray:
    n_oct = np.log2(fmax / fmin)
    n = max(2, int(round(n_oct * points_per_octave)))
    return np.geomspace(fmin, fmax, n)


def next_pow2(n: int) -> int:
    return 1 << (int(n) - 1).bit_length()


def hann_edge_gate(length: int, taper_frac: float = 0.10) -> np.ndarray:
    """Box gate with half-cosine tapered edges (limits leakage at gate start/end)."""
    if length <= 4:
        return np.ones(length)
    tap = max(1, int(length * taper_frac))
    g = np.ones(length)
    ramp = 0.5 * (1 - np.cos(np.pi * np.arange(tap) / tap))
    g[:tap] = ramp
    g[-tap:] = ramp[::-1]
    return g


def smooth_to_grid(power: np.ndarray, bin_freqs: np.ndarray,
                   grid: np.ndarray, half_oct: float = 1.0 / 24.0) -> np.ndarray:
    """Average power onto a log-frequency grid (+/- half_oct around each point)."""
    lo = np.maximum(grid / 2 ** half_oct, bin_freqs[1])
    hi = np.maximum(grid * 2 ** half_oct, bin_freqs[1] * 2)
    i0 = np.searchsorted(bin_freqs, lo, side='left')
    i1 = np.searchsorted(bin_freqs, hi, side='right')
    out = np.empty(len(grid))
    n_bins = len(power)
    for i, (a, b) in enumerate(zip(i0, i1)):
        a = min(a, n_bins - 1)
        b = max(b, a + 1)
        out[i] = power[a:b].mean()
    return out


def to_db(power: np.ndarray, floor: float = 1e-300) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(power, floor))


def fft_power_db(x: np.ndarray, sr: int, nfft: int) -> tuple[np.ndarray, np.ndarray]:
    """One-sided power spectrum (native bins) and its bin frequencies."""
    seg = x - x.mean()
    spec = np.fft.rfft(seg, nfft)
    power = spec.real ** 2 + spec.imag ** 2
    return power, np.fft.rfftfreq(nfft, 1.0 / sr)


def profile_gate_params(profile: str) -> tuple[float, float, float]:
    """(hop_ms, min_gate_ms) per named profile."""
    table = {
        'low_end': (10.0, 100.0),
        'balanced': (5.0, 40.0),
        'high_res': (2.5, 15.0),
        'transient': (2.5, 8.0),
    }
    return table.get(profile, (5.0, 40.0))
