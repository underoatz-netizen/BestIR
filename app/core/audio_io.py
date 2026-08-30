"""Audio file loading for impulse responses."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

AUDIO_EXTENSIONS = {'.wav', '.wave', '.flac', '.aif', '.aiff'}


class AudioLoadError(RuntimeError):
    pass


def load_ir(path: str | Path) -> tuple[np.ndarray, int]:
    """Load an IR file as float64 shaped (n_samples, channels) plus sample rate."""
    try:
        data, sr = sf.read(str(path), dtype='float64', always_2d=True)
    except Exception as exc:
        raise AudioLoadError(f'Cannot read {path}: {exc}') from exc
    if data.shape[0] < 16:
        raise AudioLoadError(f'{path}: too short to be an impulse response')
    return data, int(sr)
