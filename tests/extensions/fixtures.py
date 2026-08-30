"""Deterministic synthetic fixtures for extension tests (plan section 13).

Unit tests must NOT depend on the licensed IR/ library.
"""
from __future__ import annotations

import numpy as np

SR = 48000


def _ir(spec_list, n=9600, sr=SR, seed=0):
    """Sum of damped cosines (sharp onset) + noise floor.

    spec = (freq, amp, tau_s, delay_s). Cosine phase makes the onset
    unambiguous (full amplitude at the start sample).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    y = np.zeros(n)
    for f, amp, tau, delay in spec_list:
        start = int(delay * sr)
        tt = t[: n - start]
        y[start:] += amp * np.cos(2 * np.pi * f * tt) * np.exp(-tt / max(tau, 1e-6))
    y += rng.standard_normal(n) * 1e-5   # tiny noise floor
    return y


def dirac(n=9600, sr=SR, delay_s=0.001, invert=False, frac_samples=0.0):
    """Single-sample impulse (or fractional-delay broadband pulse)."""
    y = np.zeros(n)
    i = int(delay_s * sr)
    if frac_samples == 0.0:
        y[i] = -1.0 if invert else 1.0
        return y
    # hann-windowed sinc = broadband fractional-delay impulse
    taps = np.arange(-8, 9)
    x = (delay_s * sr) - i - taps
    kernel = np.sinc(x) * 0.5 * (1 + np.cos(np.pi * x / 9))
    for k, tap in enumerate(taps):
        j = i + int(tap)
        if 0 <= j < n:
            y[j] += kernel[k]
    if invert:
        y *= -1.0
    return y


def lowpassed_click(cutoff_hz=1500, n=9600, sr=SR):
    imp = dirac(n=n, sr=sr, delay_s=0.001)
    a = np.exp(-2 * np.pi * cutoff_hz / sr)
    out = np.empty_like(imp)
    acc = 0.0
    b = 1 - a
    for i, v in enumerate(imp):
        acc = b * v + a * acc
        out[i] = acc
    return out


def decay_fixture(freq_hz=80.0, tau_s=0.02, n=24000, sr=SR, delay_ms=1.0):
    """Damped sinusoid with a known decay time constant."""
    return _ir([(freq_hz, 1.0, tau_s, delay_ms / 1000.0)], n=n, sr=sr)


def boxy_fixture(boxy_hz=300.0, tau_s=0.08, n=24000, sr=SR):
    """Broadband click plus a persistent resonance inside a chosen band."""
    click = lowpassed_click(3000, n=n, sr=sr) * 0.5
    ring = _ir([(boxy_hz, 0.8, tau_s, 0.001)], n=n, sr=sr)
    return click + ring


def clean_fixture(n=24000, sr=SR):
    """Broadband click with only fast-decay content (no persistent band ring)."""
    click = lowpassed_click(3000, n=n, sr=sr) * 0.5
    fast = _ir([(300.0, 0.4, 0.004, 0.001)], n=n, sr=sr)   # same band, tiny tau
    return click + fast


def stereo_pair_fixture(delay_samples=7, invert_ch2=False, n=9600, sr=SR):
    base = decay_fixture(120.0, 0.01, n=n, sr=sr)
    ch1 = base
    ch2 = np.roll(base, delay_samples) * (-1.0 if invert_ch2 else 1.0)
    ch2[:delay_samples] = 0.0
    return np.stack([ch1, ch2], axis=1)


def attack_fixture(attack_ms=1.0, carrier_hz=800.0, n=24000, sr=SR):
    """Sinusoid with a hann-ramp attack envelope — has a genuine 10-90% rise."""
    t = np.arange(n) / sr
    na = max(2, int(attack_ms / 1000 * sr))
    env = np.ones(n)
    env[:na] = 0.5 * (1 - np.cos(np.pi * np.arange(na) / na))
    env *= np.exp(-t / 0.05)
    return np.sin(2 * np.pi * carrier_hz * t) * env * (t >= 0.001)


def truncated_fixture(n=1200, sr=SR):
    """Cabinet-style decaying tail cut off early (not a valid reverb measure)."""
    y = decay_fixture(100.0, 0.06, n=24000, sr=sr)[:n]
    return y


def exp_t60_fixture(t60_ms=100.0, n=24000, sr=SR):
    """Exponential amplitude decay: T60 amplitude = tau * ln(1000)."""
    tau = t60_ms / 1000.0 / np.log(1000.0) * np.log(1000.0)  # placeholder
    tau = t60_ms / 1000.0 / 6.9078     # amplitude e^(-t/tau) -> -60 dB at 6.9078 tau
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * 200.0 * t) * np.exp(-t / tau) * (t > 0.001)


def silent(n=9600):
    return np.zeros(n)


def clipped(n=9600, sr=SR):
    y = decay_fixture(100.0, 0.02, n=n, sr=sr)
    return np.clip(y * 50.0, -1.0, 1.0)


def with_nan(n=9600):
    y = decay_fixture(100.0, 0.02, n=n)
    y[100] = np.nan
    return y
