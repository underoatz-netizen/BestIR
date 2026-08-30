"""WP-01 gates: contract immutability, adapter isolation, sidecar cache."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.adapters import LegacyIRAdapter, make_read_only
from app.extensions.cache import FingerprintCache
from app.extensions.contracts import (ALGO_VERSION, AnalysisStatus, AudioBuffer,
                                      FeatureValue, PreprocessingConfig,
                                      ResponseFingerprint, SourceKey,
                                      config_hash)
from tests.synth import synth_ir, write_wav


def _src_key():
    return SourceKey(path='C:/x/a.wav', mtime_ns=1, size=2,
                     sample_rate=48000, channels=1)


# ---- contracts -----------------------------------------------------------------
def test_source_key_signature_stable():
    a = _src_key().signature()
    b = _src_key().signature()
    assert a == b and len(a) == 40


def test_frozen_dataclasses_reject_mutation():
    key = _src_key()
    with pytest.raises(Exception):
        key.size = 99
    cfg = PreprocessingConfig()
    with pytest.raises(Exception):
        cfg.dc_remove = False


def test_config_hash_changes_with_content():
    a = PreprocessingConfig()
    b = PreprocessingConfig(dc_remove=False)
    assert a.config_hash() != b.config_hash()
    assert a.config_hash() == PreprocessingConfig().config_hash()


def test_feature_value_and_fingerprint_json_roundtrip():
    fp = ResponseFingerprint(
        key=_src_key(), version=ALGO_VERSION, cfg_hash='abc',
        transient={'ttp': FeatureValue(1.5, True)},
        decay={'d20': FeatureValue(None, False, 'noise dominated')},
    )
    fp2 = ResponseFingerprint.from_json(fp.to_json())
    assert fp2.transient['ttp'].value == 1.5
    assert fp2.decay['d20'].valid is False
    assert fp2.decay['d20'].note == 'noise dominated'
    assert fp2.key == _src_key()


def test_read_only_arrays():
    arr = make_read_only(np.zeros(4))
    with pytest.raises(ValueError):
        arr[0] = 1.0


# ---- adapter ---------------------------------------------------------------------
def test_adapter_loads_read_only_buffer(tmp_path):
    path = Path(write_wav(tmp_path / 'a.wav', synth_ir(seed=3), 48000))
    buf = LegacyIRAdapter().load_path(str(path))
    assert isinstance(buf, AudioBuffer)
    assert buf.data.shape[1] == 1
    assert buf.data.dtype == np.float64
    assert not buf.data.flags.writeable
    assert buf.key.sample_rate == 48000
    assert buf.key.channels == 1
    assert len(buf.key.signature()) == 40


def test_adapter_rejects_bad_file(tmp_path):
    bad = tmp_path / 'bad.wav'
    bad.write_bytes(b'not a wav')
    buf, status = LegacyIRAdapter().try_load_path(str(bad))
    assert buf is None and status == AnalysisStatus.UNREADABLE


def test_adapter_path_is_absolute(tmp_path):
    path = Path(write_wav(tmp_path / 'a.wav', synth_ir(seed=5), 48000))
    buf = LegacyIRAdapter().load_path(str(path))
    assert Path(buf.key.path).is_absolute()


def test_adapter_does_not_mutate_source_file(tmp_path):
    path = Path(write_wav(tmp_path / 'a.wav', synth_ir(seed=4), 48000))
    before = path.read_bytes()
    adapter = LegacyIRAdapter()
    buf = adapter.load_path(str(path))
    mutated = buf.data * 2.0        # attempt in-place style math
    assert path.read_bytes() == before
    assert mutated is not buf.data


# ---- cache ---------------------------------------------------------------------
def _fingerprint(path='C:/x/a.wav'):
    return ResponseFingerprint(
        key=SourceKey(path=path, mtime_ns=11, size=22, sample_rate=48000,
                      channels=2),
        version=ALGO_VERSION, cfg_hash='cfg1',
        transient={'crest': FeatureValue(3.2, True)},
        decay={'d20_low': FeatureValue(48.0, True)},
        phase={'gd_spread': FeatureValue(None, False, 'no valid bins')})


def test_cache_roundtrip(tmp_path):
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    fp = _fingerprint()
    cache.put(fp, 'cfg1')
    got = cache.get(fp.key.signature(), 'cfg1')
    assert got is not None
    assert got.decay['d20_low'].value == 48.0
    assert got.key == fp.key
    assert cache.count() == 1


def test_cache_miss_on_cfg_or_mtime_change(tmp_path):
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    fp = _fingerprint()
    cache.put(fp, 'cfg1')
    assert cache.get(fp.key.signature(), 'cfg2') is None
    moved = ResponseFingerprint(
        key=SourceKey(fp.key.path, fp.key.mtime_ns + 5, fp.key.size,
                      fp.key.sample_rate, fp.key.channels),
        version=ALGO_VERSION, cfg_hash='cfg1')
    assert cache.get(moved.key.signature(), 'cfg1') is None


def test_cache_corrupt_db_recovers(tmp_path):
    db = tmp_path / 'fp.db'
    db.write_bytes(b'this is not sqlite' * 100)
    cache = FingerprintCache(str(db))
    fp = _fingerprint()
    cache.put(fp, 'cfg1')
    assert cache.get(fp.key.signature(), 'cfg1') is not None
    assert cache.count() == 1
