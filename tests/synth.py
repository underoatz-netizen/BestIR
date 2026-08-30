"""Shared helpers to synthesize IRs with known spectral shapes for testing."""
from __future__ import annotations

import numpy as np
import soundfile as sf

# Control points for synth_ir: (freq, dB) anchors interpolated on a log-f axis
POINTS_DEFAULT = [20, 60, 120, 350, 1000, 3500, 8000, 20000]


def synth_ir(sr: int = 48000, n: int = 9600, anchors_db=None,
             anchor_freqs=None, delay_ms: float = 1.0, seed: int = 0,
             channels: int = 1) -> np.ndarray:
    """Build an IR whose magnitude follows the given anchor points (linear phase)."""
    if anchor_freqs is None:
        anchor_freqs = POINTS_DEFAULT
    if anchors_db is None:
        anchors_db = [0.0] * len(anchor_freqs)
    rng = np.random.default_rng(seed)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    mag = 10 ** (np.interp(f, anchor_freqs, anchors_db,
                           left=anchors_db[0], right=anchors_db[-1]) / 20.0)
    d = int(delay_ms / 1000 * sr)  # linear phase -> audible onset at d samples
    spec = mag * np.exp(-2j * np.pi * np.arange(len(f)) * d / n)
    ir = np.fft.irfft(spec, n)
    ir /= np.max(np.abs(ir)) + 1e-12
    if channels > 1:
        variants = [ir]
        for c in range(1, channels):
            rng2 = np.random.default_rng(seed + c)
            spec2 = mag * np.exp(-2j * np.pi * np.arange(len(f)) * (d + int(rng2.integers(3, 40))) / n)
            ir2 = np.fft.irfft(spec2, n)
            ir2 /= np.max(np.abs(ir2)) + 1e-12
            variants.append(ir2)
        ir = np.stack(variants, axis=1)
    return ir


def one_pole_lowpass_ir(cutoff_hz: float, sr: int = 48000, n: int = 9600) -> np.ndarray:
    impulse = np.zeros(n)
    impulse[int(0.001 * sr)] = 1.0
    a = np.exp(-2 * np.pi * cutoff_hz / sr)
    out = np.empty_like(impulse)
    acc = 0.0
    b = 1 - a
    for i, x in enumerate(impulse):
        acc = b * x + a * acc
        out[i] = acc
    return out


def write_wav(path, data: np.ndarray, sr: int = 48000) -> str:
    if data.ndim == 1:
        data = data[:, None]
    sf.write(str(path), data, sr, subtype='PCM_24')
    return str(path)
