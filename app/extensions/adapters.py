"""Adapter from legacy library records to extension buffers (WP-01)."""
from __future__ import annotations

import os

import numpy as np

from ..core.audio_io import AudioLoadError, load_ir
from .contracts import AnalysisStatus, AudioBuffer, SourceKey


class LegacyIRAdapter:
    """Loads an IR file through the legacy loader and wraps it read-only.

    The adapter never writes to the source and never mutates legacy objects.
    """

    def load_path(self, path: str) -> AudioBuffer:
        data, sr = load_ir(path)          # raises AudioLoadError
        stat = os.stat(path)
        key = SourceKey(path=os.path.abspath(path), mtime_ns=stat.st_mtime_ns,
                        size=stat.st_size, sample_rate=sr,
                        channels=int(data.shape[1]))
        data = np.ascontiguousarray(data, dtype=np.float64)
        data.setflags(write=False)
        return AudioBuffer(key=key, data=data)

    def try_load_path(self, path: str):
        """Return (buffer, None) or (None, status) without raising."""
        try:
            return self.load_path(path), None
        except AudioLoadError:
            return None, AnalysisStatus.UNREADABLE
        except OSError:
            return None, AnalysisStatus.UNREADABLE


def make_read_only(arr: np.ndarray) -> np.ndarray:
    """Flag an array non-writeable (used for data handed across modules)."""
    arr = np.ascontiguousarray(arr)
    arr.setflags(write=False)
    return arr
