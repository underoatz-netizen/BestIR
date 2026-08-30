import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from app.core.cache import LibraryCache
from app.core.scanner import find_ir_files, scan_library
from tests.synth import synth_ir, write_wav


def _make_lib(tmp_path):
    ir = synth_ir(anchors_db=[0, 1, 0, -1, 0, 1, 0, 1])
    (tmp_path / 'sub').mkdir(exist_ok=True)
    write_wav(tmp_path / 'a.wav', ir)
    write_wav(tmp_path / 'sub' / 'b.wav', ir)
    (tmp_path / '.hidden.wav').write_bytes(b'x')
    (tmp_path / 'notes.txt').write_text('skip me')
    return ir


def test_find_ir_files_skips_junk(tmp_path):
    _make_lib(tmp_path)
    files = find_ir_files([str(tmp_path)])
    names = [Path(f).name for f in files]
    assert names == ['a.wav', 'b.wav']


def test_cache_roundtrip_and_invalidation(tmp_path):
    ir = synth_ir(anchors_db=[0, 1, 0, -1, 0, 1, 0, 1])
    path = write_wav(tmp_path / 'a.wav', ir)
    cache_file = tmp_path / 'cache.json'

    cache = LibraryCache(cache_file)
    res1 = scan_library([str(tmp_path)], cache)[0]
    assert len(cache) == 1

    cache2 = LibraryCache(cache_file)
    stat = os.stat(path)
    hit = cache2.get(path, stat.st_mtime_ns, stat.st_size)
    assert hit is not None
    assert np.allclose(hit.curve_db, res1.curve_db)

    # bump mtime -> entry invalidated
    s = os.stat(path)
    os.utime(path, ns=(s.st_atime_ns, s.st_mtime_ns + 10_000_000))
    stat = os.stat(path)
    assert cache2.get(path, stat.st_mtime_ns, stat.st_size) is None


def test_scan_uses_cache_on_second_pass(tmp_path):
    _make_lib(tmp_path)
    cache = LibraryCache(tmp_path / 'cache.json')

    calls = []
    real_analyze = None
    import app.core.scanner as scanner
    real_analyze = scanner.analyze_file

    def counting(path):
        calls.append(path)
        return real_analyze(path)

    scanner.analyze_file = counting
    try:
        scan_library([str(tmp_path)], cache)
        assert len(calls) == 2
        scan_library([str(tmp_path)], cache)
        assert len(calls) == 2  # second pass fully served from cache
    finally:
        scanner.analyze_file = real_analyze
