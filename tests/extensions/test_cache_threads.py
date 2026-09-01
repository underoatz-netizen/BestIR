"""B14 regression tests: SQLite cache thread-safety (extension-only).

These exercise the actual cross-thread contract of FingerprintCache that the
sequential cache tests in test_contracts.py cannot see: a cache instance
created on one thread must be readable/writable from real worker threads, and
concurrent writers must all persist (no silent drops).

The B14 failure mode was: the single sqlite3 connection was opened on the
GUI thread; any worker-thread access raised sqlite3.ProgrammingError which the
broad ``except sqlite3.Error`` swallowed, so worker reads always returned None
and worker inserts were silently dropped.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.extensions.cache import FingerprintCache
from app.extensions.contracts import (ALGO_VERSION, FeatureValue,
                                      ResponseFingerprint, SourceKey)


def _fingerprint(path: str, d20: float = 48.0) -> ResponseFingerprint:
    return ResponseFingerprint(
        key=SourceKey(path=path, mtime_ns=11, size=22, sample_rate=48000,
                      channels=2),
        version=ALGO_VERSION, cfg_hash='cfg1',
        transient={'crest': FeatureValue(3.2, True)},
        decay={'d20_low': FeatureValue(d20, True)},
        phase={'gd_spread': FeatureValue(None, False, 'no valid bins')})


def _sig(fp: ResponseFingerprint) -> str:
    return fp.key.signature()


def test_worker_reads_main_thread_hit(tmp_path):
    """B14 core: a worker must see what the main thread already cached."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))   # opened on this thread
    fp = _fingerprint('C:/x/a.wav')
    cache.put(fp, 'cfg1')
    assert cache.get(_sig(fp), 'cfg1') is not None      # main-thread hit

    result = {}

    def worker():
        result['hit'] = cache.get(_sig(fp), 'cfg1') is not None

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result['hit'] is True


def test_worker_insert_persists_and_main_reads_back(tmp_path):
    """B14 core: a worker insert must actually be stored and visible later."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    fp = _fingerprint('C:/x/worker-insert.wav', d20=55.0)

    def worker():
        cache.put(fp, 'cfg1')

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    got = cache.get(_sig(fp), 'cfg1')
    assert got is not None
    assert got.decay['d20_low'].value == 55.0
    assert cache.count() == 1


def test_worker_insert_visible_to_other_worker_thread(tmp_path):
    """A write by one worker is visible to a different worker thread."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    fp = _fingerprint('C:/x/worker-a.wav')
    results = {}

    def putter():
        cache.put(fp, 'cfg1')

    def getter():
        results['hit'] = cache.get(_sig(fp), 'cfg1') is not None

    ta = threading.Thread(target=putter)
    tb = threading.Thread(target=getter)
    ta.start()
    ta.join()
    tb.start()
    tb.join()
    assert results['hit'] is True


def test_concurrent_writes_all_persist(tmp_path):
    """Concurrent writers from many threads: no insert is silently dropped."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    threads = 6
    per_thread = 20
    barrier = threading.Barrier(threads)
    errors: list[Exception] = []

    def worker(seed: int):
        try:
            barrier.wait(timeout=30)
            for i in range(per_thread):
                fp = _fingerprint(f'C:/x/t{seed}-{i}.wav', d20=float(seed + i))
                cache.put(fp, 'cfg1')
        except Exception as exc:   # pragma: no cover - failure evidence
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(s,)) for s in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errors
    assert cache.count() == threads * per_thread
    for s in range(threads):
        fp = _fingerprint(f'C:/x/t{s}-{per_thread - 1}.wav')
        assert cache.get(_sig(fp), 'cfg1') is not None


def test_concurrent_read_write_burst_no_silent_failure(tmp_path):
    """Mixed read/write/count from parallel threads stays consistent."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    n_threads = 5
    barrier = threading.Barrier(n_threads)
    errors: list[Exception] = []

    def worker(seed: int):
        try:
            barrier.wait(timeout=30)
            for i in range(15):
                fp = _fingerprint(f'C:/x/burst-{seed}-{i}.wav')
                cache.put(fp, 'cfg1')
                cache.get(_sig(fp), 'cfg1')
                cache.count()
        except Exception as exc:   # pragma: no cover - failure evidence
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(s,)) for s in range(n_threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errors
    assert cache.count() == n_threads * 15


def test_threadpool_worker_read_write(tmp_path):
    """Mirrors the review probe: ThreadPoolExecutor worker hits a main put."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    fp = _fingerprint('C:/x/pool.wav')
    cache.put(fp, 'cfg1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker_read = pool.submit(cache.get, _sig(fp), 'cfg1').result()
        pool.submit(cache.put,
                    _fingerprint('C:/x/pool-2.wav', d20=60.0), 'cfg1').result()
    assert worker_read is not None
    assert cache.get(_sig(_fingerprint('C:/x/pool-2.wav')), 'cfg1') is not None
    assert cache.count() == 2


def test_close_prevents_all_threads(tmp_path):
    """After close(), every thread sees the cache as unavailable (no errors)."""
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    cache.put(_fingerprint('C:/x/before.wav'), 'cfg1')
    cache.close()

    assert cache.get(_sig(_fingerprint('C:/x/before.wav')), 'cfg1') is None
    assert cache.count() == 0
    cache.put(_fingerprint('C:/x/after.wav'), 'cfg1')   # no-op, no raise
    assert cache.count() == 0

    result = {}

    def worker():
        result['read'] = cache.get(_sig(_fingerprint('C:/x/before.wav')),
                                   'cfg1') is not None
        result['count'] = cache.count()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result == {'read': False, 'count': 0}


def test_two_instances_share_file_across_threads(tmp_path):
    """Distinct cache instances on distinct threads share one DB file."""
    db = str(tmp_path / 'fp.db')
    main_cache = FingerprintCache(db)
    fp = _fingerprint('C:/x/shared.wav')
    main_cache.put(fp, 'cfg1')

    result = {}

    def worker():
        other = FingerprintCache(db)   # worker-owned instance, same file
        result['hit'] = other.get(_sig(fp), 'cfg1') is not None
        other.put(_fingerprint('C:/x/shared-2.wav'), 'cfg1')
        other.close()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert result['hit'] is True
    assert main_cache.get(_sig(_fingerprint('C:/x/shared-2.wav')),
                          'cfg1') is not None
    assert main_cache.count() == 2


def test_corrupt_db_recovers_from_worker_thread(tmp_path):
    """Corrupt file is recreated on first worker access, then usable."""
    db = tmp_path / 'fp.db'
    db.write_bytes(b'this is not sqlite' * 100)
    cache = FingerprintCache(str(db))
    fp = _fingerprint('C:/x/corrupt-worker.wav')
    result = {}

    def worker():
        cache.put(fp, 'cfg1')
        result['hit'] = cache.get(_sig(fp), 'cfg1') is not None

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert result['hit'] is True
    assert cache.get(_sig(fp), 'cfg1') is not None
    assert cache.count() == 1