"""In-app audition: convolve a test signal with an IR and play it back."""
from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve, resample_poly

from .audio_io import load_ir

BUILTIN_SOURCES = ('Pink noise', 'Power chord DI', 'Palm mute chug')

RMS_TARGET = 0.1     # playback level-match target (~ -20 dBFS RMS)
PEAK_GUARD = 0.89    # never let peaks exceed this
LOOP_SECONDS = 30.0  # when looping, tile the render to this length


class AuditionEngine:
    """Plays a dry test signal through an IR. Gracefully degrades without a device."""

    def __init__(self):
        try:
            import sounddevice as sd
            out = sd.query_devices(kind='output')
            self.device_sr = int(out['default_samplerate'])
            self._sd = sd
            self.available = True
        except Exception:
            self._sd = None
            self.device_sr = 48000
            self.available = False
        self._test_cache: dict[tuple[str, int], np.ndarray] = {}
        self._custom: tuple[np.ndarray, int] | None = None
        self._di: tuple[np.ndarray, int] | None = None
        self.playing_path: str | None = None

    # ---- test signals ------------------------------------------------------
    def set_custom_signal(self, data: np.ndarray, sr: int) -> None:
        self._custom = (data, sr)

    def set_di_signal(self, data: np.ndarray, sr: int) -> None:
        self._di = (data, sr)

    def clear_di_signal(self) -> None:
        self._di = None

    def test_signal(self, name: str, sr: int) -> np.ndarray:
        """Mono float64 test signal at `sr` (cached per name+sr)."""
        if name == 'Recorded DI':
            if self._di is None:
                raise RuntimeError('No DI recorded — use the Tone Match tab first')
            data, src_sr = self._di
            return _resample(_mono(data), src_sr, sr)
        if name == 'Custom WAV':
            if self._custom is None:
                raise RuntimeError('No custom WAV loaded')
            data, src_sr = self._custom
            return _resample(_mono(data), src_sr, sr)
        key = (name, sr)
        if key not in self._test_cache:
            if name == 'Pink noise':
                sig = _pink_noise(2.0, sr)
            elif name == 'Power chord DI':
                sig = _power_chord(2.0, sr)
            elif name == 'Palm mute chug':
                sig = _palm_mute(1.2, sr)
            else:
                raise ValueError(f'Unknown test source: {name}')
            self._test_cache[key] = sig
        return self._test_cache[key]

    # ---- playback ------------------------------------------------------------
    def play(self, ir_path: str, source: str, level_match: bool = True,
             loop: bool = True, volume: float = 1.0) -> None:
        if not self.available:
            return
        sig = self.test_signal(source, self.device_sr)
        data, ir_sr = load_ir(ir_path)
        if data.shape[1] > 1:
            chans = [_resample(data[:, c], ir_sr, self.device_sr)
                     for c in range(data.shape[1])]
            out = np.stack([fftconvolve(sig, ch) for ch in chans], axis=1)
        else:
            ir = _resample(data[:, 0], ir_sr, self.device_sr)
            out = fftconvolve(sig, ir)[:, None]
        if loop:
            reps = int(np.ceil(LOOP_SECONDS * self.device_sr / len(out)))
            out = np.tile(out, (reps, 1))
        out = _fade_edges(out, int(0.005 * self.device_sr))
        out *= volume
        if level_match:
            out = _level_match(out)
        self._sd.stop()
        self._sd.play(out, self.device_sr)
        self.playing_path = ir_path

    def stop(self) -> None:
        if self.available and self._sd is not None:
            self._sd.stop()
        self.playing_path = None


# ---- helpers -----------------------------------------------------------------
def _mono(data: np.ndarray) -> np.ndarray:
    return data.mean(axis=1) if data.ndim > 1 else data


def _resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return x
    from math import gcd
    g = gcd(int(src_sr), int(dst_sr))
    return resample_poly(x, dst_sr // g, src_sr // g)


def _fade_edges(x: np.ndarray, n: int) -> np.ndarray:
    n = min(n, max(1, len(x) // 4))
    ramp = np.linspace(0.0, 1.0, n)[:, None]
    x = x.copy()
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def _level_match(out: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(out ** 2)))
    if rms > 0:
        out = out * (RMS_TARGET / rms)
    peak = float(np.max(np.abs(out)))
    if peak > PEAK_GUARD:
        out = out * (PEAK_GUARD / peak)
    return out


def _pink_noise(seconds: float, sr: int) -> np.ndarray:
    n = int(seconds * sr)
    rng = np.random.default_rng(3)
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    f[0] = f[1]
    spec /= np.sqrt(f)          # energy -> 1/f
    out = np.fft.irfft(spec, n)
    return out / (np.max(np.abs(out)) + 1e-12) * 0.9


def _additive_saw(f0: float, seconds: float, sr: int, n_harm: int = 48,
                  rolloff: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    out = np.zeros_like(t)
    nyq = sr / 2
    for k in range(1, min(n_harm, int(nyq / f0)) + 1):
        out += np.sin(2 * np.pi * f0 * k * t) / (k ** rolloff)
    return out / (np.max(np.abs(out)) + 1e-12)


def _power_chord(seconds: float, sr: int) -> np.ndarray:
    """Synthesized DI power chord: E2 root + B2 fifth + E3 octave, slight detune."""
    cents = 2 ** (3.0 / 1200.0)  # +/- 3 cents detune pair
    sig = (_additive_saw(82.41, seconds, sr) + _additive_saw(82.41 * cents, seconds, sr)
           + _additive_saw(123.47, seconds, sr) + _additive_saw(123.47 / cents, seconds, sr)
           + _additive_saw(164.81, seconds, sr))
    t = np.arange(len(sig)) / sr
    env = np.minimum(t / 0.01, 1.0) * np.exp(-t / 1.5)
    sig = sig * env
    return sig / (np.max(np.abs(sig)) + 1e-12) * 0.9


def _palm_mute(seconds: float, sr: int) -> np.ndarray:
    """Low E1 chug with fast decay — exposes low-end behavior."""
    sig = _additive_saw(41.20, seconds, sr, rolloff=1.6)
    t = np.arange(len(sig)) / sr
    env = np.minimum(t / 0.005, 1.0) * np.exp(-t / 0.16)
    sig = sig * env
    # re-trigger every 0.4 s
    period = int(0.4 * sr)
    n = len(sig)
    full = np.zeros(n)
    start = 0
    while start < n:
        full[start:start + min(period, n - start)] += sig[:min(period, n - start)]
        start += period
    return full / (np.max(np.abs(full)) + 1e-12) * 0.9
