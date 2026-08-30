"""SQLite sidecar cache for response fingerprints (WP-01).

Keyed by (signature, algo_version, cfg_hash). Corrupt database files are
recreated silently; a failed cache read is never treated as a valid result.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
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
    def __init__(self, path: str | None = None):
        if path is None:
            base = os.environ.get('LOCALAPPDATA', tempfile.gettempdir())
            path = os.path.join(base, 'BestIR', 'fingerprints.db')
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            conn = sqlite3.connect(self.path)
            conn.executescript(_SCHEMA)
            conn.commit()
            self._conn = conn
        except sqlite3.Error:
            # corrupt file -> close the stuck handle, recreate once
            try:
                conn.close()
            except Exception:
                pass
            try:
                if os.path.exists(self.path):
                    os.replace(self.path, f'{self.path}.corrupt-{time.time()}')
                conn = sqlite3.connect(self.path)
                conn.executescript(_SCHEMA)
                conn.commit()
                self._conn = conn
            except (sqlite3.Error, OSError):
                self._conn = None   # cache unavailable; service works uncached

    def get(self, signature: str, cfg_hash: str,
            algo: str = ALGO_VERSION) -> ResponseFingerprint | None:
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(
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
        if self._conn is None:
            return
        try:
            self._conn.execute(
                'INSERT OR REPLACE INTO fingerprints '
                '(signature, algo, cfg_hash, json, created) VALUES (?,?,?,?,?)',
                (fingerprint.key.signature(), fingerprint.version, cfg_hash,
                 fingerprint.to_json(), time.time()))
            self._conn.commit()
        except (sqlite3.Error, TypeError, ValueError):
            pass   # cache is best-effort

    def count(self) -> int:
        if self._conn is None:
            return 0
        try:
            row = self._conn.execute('SELECT COUNT(*) FROM fingerprints').fetchone()
            return int(row[0])
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
