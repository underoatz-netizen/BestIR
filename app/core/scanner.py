"""Folder scanning + cached analysis of a whole IR library."""
from __future__ import annotations

import os
from pathlib import Path

from .analysis import (AnalysisResult, analyze_file, compute_library_stats,
                       derive_tags)
from .audio_io import AUDIO_EXTENSIONS
from .cache import LibraryCache

ProgressFn = object  # callable(done: int, total: int, current_path: str)


def find_ir_files(roots: list[str]) -> list[str]:
    """Recursively collect IR audio files under the given roots, skipping dot-files."""
    found: list[str] = []
    seen_roots = set()
    for root in roots:
        rp = Path(root)
        key = str(rp).lower()
        if key in seen_roots or not rp.is_dir():
            continue
        seen_roots.add(key)
        for dirpath, dirnames, filenames in os.walk(rp):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for name in sorted(filenames):
                if name.startswith('.'):
                    continue
                if Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                    found.append(str(Path(dirpath) / name))
    return sorted(found)


def scan_library(roots: list[str], cache: LibraryCache,
                 progress=None, force: bool = False) -> list[AnalysisResult]:
    """Analyze every IR under `roots`, reusing cache entries unless `force`.

    `progress(done, total, current_path)` is called after each file.
    """
    files = find_ir_files(roots)
    results: list[AnalysisResult] = []
    for done, path in enumerate(files, start=1):
        try:
            stat = os.stat(path)
        except OSError:
            continue
        result = None if force else cache.get(path, stat.st_mtime_ns, stat.st_size)
        if result is None:
            try:
                result = analyze_file(path)
                cache.put(result, stat.st_mtime_ns, stat.st_size)
            except Exception:
                continue  # unreadable/corrupt file — skip it
        results.append(result)
        if progress is not None:
            progress(done, len(files), path)

    # Tone tags relative to the library's own median character (falls back to
    # absolute rules for small libraries).
    stats = compute_library_stats(results)
    for result in results:
        result.tags = derive_tags(result, stats)

    cache.save()
    return results
