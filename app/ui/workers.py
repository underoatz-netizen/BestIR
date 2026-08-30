"""Background workers: library scanning and audio recording."""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import QThread, Signal

from app.core.cache import LibraryCache
from app.core.analysis import AnalysisResult
from app.core.scanner import scan_library


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, folders: list[str], cache: LibraryCache, force: bool = False,
                 parent=None):
        super().__init__(parent)
        self.folders = folders
        self.cache = cache
        self.force = force

    def run(self):
        try:
            results = scan_library(
                self.folders, self.cache, force=self.force,
                progress=lambda d, t, p: self.progress.emit(d, t, p))
        except Exception as exc:  # surface, don't crash the thread
            self.failed.emit(str(exc))
            return
        self.done.emit(results)


class RecordWorker(QThread):
    """Records mono audio from the default input device for up to `seconds`."""
    progress = Signal(float)
    done = Signal(object, int)   # (mono float64 data, sample rate)
    failed = Signal(str)

    def __init__(self, seconds: float, parent=None):
        super().__init__(parent)
        self.seconds = float(seconds)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import sounddevice as sd
            dev = sd.query_devices(kind='input')
            sr = int(dev['default_samplerate'])
            chunks: list[np.ndarray] = []

            def callback(indata, frames, time_info, status):
                chunks.append(indata.copy())

            with sd.InputStream(samplerate=sr, channels=1, dtype='float32',
                                callback=callback):
                t0 = time.perf_counter()
                while not self._stop and time.perf_counter() - t0 < self.seconds:
                    time.sleep(0.05)
                    self.progress.emit(time.perf_counter() - t0)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        data = (np.concatenate(chunks)[:, 0].astype(np.float64)
                if chunks else np.zeros(0))
        self.done.emit(data, sr)


def has_input_device() -> bool:
    try:
        import sounddevice as sd
        sd.query_devices(kind='input')
        return True
    except Exception:
        return False
