"""SQLite sidecar cache for response fingerprints (WP-01).

Keyed by (signature, algo_version, cfg_hash). Corrupt database files are
recreated silently; a failed cache read is never treated as a valid result.

Thread-safety (B14): one connection per thread, opened lazily on first use.
A connection created on the GUI thread must never be touched from a worker
thread (sqlite3 enforces this and would silently miss/write nothing), so each
thread owns its own connection to the same database file. SQLite serialises
writers through file locking with a busy timeout; concurrent readers do not
block each other. ``close()`` closes every thread's connection and makes the
cache unavailable afterwards.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time

from .contracts import ALGO_VERSION, ResponseFingerprint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fingerprints (
    signature   TEXT NOT NULL,
    algo        TEXT NOT NULL,
    cfg_hash    TEXT NOT NULL,
    json        TEXT NOT NULL,
    created     REAL NOT NULL,
    PRIMARY KEY (signature, algo, cfg_hash)
);
"""


class FingerprintCache:
    def __init__(self, path: str | None = None, timeout: float = 5.0):
        if path is None:
            base = os.environ.get('LOCALAPPDATA', tempfile.gettempdir())
            path = os.path.join(base, 'BestIR', 'fingerprints.db')
        self.path = path
        self._timeout = timeout
        self._local = threading.local()
        self._conns: dict[int, sqlite3.Connection] = {}
        self._lock = threading.Lock()
        self._closed = False

    # ---- connection lifecycle (one lazy connection per thread) ----------
    @property
    def _conn(self) -> sqlite3.Connection | None:
        if self._closed:
            return None
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            return conn
        with self._lock:
            if self._closed:
                return None
            conn = self._open()
            if conn is None:
                return None
            self._local.conn = conn
            self._conns[threading.get_ident()] = conn
        return conn

    def _open(self) -> sqlite3.Connection | None:
        conn = None
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=self._timeout)
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn
        except (sqlite3.Error, OSError):
            pass   # conn still holds the stuck handle -> close it below
        # corrupt file -> close the stuck handle, recreate once
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        try:
            if os.path.exists(self.path):
                os.replace(self.path, f'{self.path}.corrupt-{time.time()}')
            conn = sqlite3.connect(self.path, timeout=self._timeout)
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn
        except (sqlite3.Error, OSError):
            return None   # cache unavailable; service works uncached

    def get(self, signature: str, cfg_hash: str,
            algo: str = ALGO_VERSION) -> ResponseFingerprint | None:
        conn = self._conn
        if conn is None:
            return None
        try:
            row = conn.execute(
                'SELECT json FROM fingerprints '
                'WHERE signature=? AND algo=? AND cfg_hash=?',
                (signature, algo, cfg_hash)).fetchone()
        except sqlite3.Error:
            return None
        if not row:
            return None
        try:
            fp = ResponseFingerprint.from_json(row[0])
            if fp.version != algo:
                return None
            return fp
        except (ValueError, KeyError, TypeError):
            return None

    def put(self, fingerprint: ResponseFingerprint, cfg_hash: str) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.execute(
                'INSERT OR REPLACE INTO fingerprints '
                '(signature, algo, cfg_hash, json, created) VALUES (?,?,?,?,?)',
                (fingerprint.key.signature(), fingerprint.version, cfg_hash,
                 fingerprint.to_json(), time.time()))
            conn.commit()
        except (sqlite3.Error, TypeError, ValueError):
            pass   # cache is best-effort

    def count(self) -> int:
        conn = self._conn
        if conn is None:
            return 0
        try:
            row = conn.execute('SELECT COUNT(*) FROM fingerprints').fetchone()
            return int(row[0])
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            conns = list(self._conns.values())
            self._conns.clear()
        self._local.conn = None
        for conn in conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
