"""Persistent analysis cache keyed by path + mtime + size."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from .analysis import AnalysisResult

CACHE_VERSION = 4

_FIELDS = (
    'path', 'sample_rate', 'channels', 'n_samples', 'length_ms',
    'effective_length_ms', 'flatness_db', 'tilt_db_oct', 'band_levels',
    'peak_freq', 'peak_db', 'notch_freq', 'notch_db',
)


class LibraryCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding='utf-8') as fh:
                doc = json.load(fh)
            if doc.get('version') == CACHE_VERSION:
                self._entries = doc.get('entries', {})
        except (OSError, ValueError):
            self._entries = {}

    def get(self, path: str, mtime_ns: int, size: int) -> AnalysisResult | None:
        entry = self._entries.get(path)
        if not entry or entry.get('mtime_ns') != mtime_ns or entry.get('size') != size:
            return None
        try:
            return AnalysisResult(
                **{k: entry[k] for k in _FIELDS},
                curve_db=np.asarray(entry['curve_db'], dtype=float),
                wave=np.asarray(entry['wave'], dtype=float),
            )
        except (KeyError, TypeError):
            return None

    def put(self, result: AnalysisResult, mtime_ns: int, size: int) -> None:
        self._entries[result.path] = {
            'mtime_ns': mtime_ns, 'size': size,
            **{k: getattr(result, k) for k in _FIELDS},
            'curve_db': [float(v) for v in result.curve_db],
            'wave': [float(v) for v in result.wave],
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {'version': CACHE_VERSION, 'entries': self._entries}
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(doc, fh)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def __len__(self) -> int:
        return len(self._entries)
