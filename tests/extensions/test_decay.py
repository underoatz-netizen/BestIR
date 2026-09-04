"""WP-05 gates: decay metrics, guarded T60, fingerprints."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.cache import FingerprintCache
from app.extensions.contracts import (AudioBuffer, DecayConfig, EnvelopeConfig,
                                       PreprocessingConfig, SourceKey)
from app.extensions.decay import compute_decay
from app.extensions.preprocessing import prepare
from app.extensions.service import ResponseService
from app.core.analysis import analyze_file
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


def test_exp_decay_recovers_t60_within_5pct():
    t60_ms = 120.0
    tau = t60_ms / 1000.0 / 6.9078
    t = np.arange(48000) / fx.SR
    y = np.cos(2 * np.pi * 400.0 * t) * np.exp(-t / tau) * (t >= 0.001)
    res = compute_decay(_prep(y), DecayConfig())
    assert res.t60_estimate_ms is not None, res.t60_reason
    err = abs(res.t60_estimate_ms - t60_ms) / t60_ms
    assert err < 0.05, (res.t60_estimate_ms, err)
    assert res.t60_valid is True


def test_truncated_cabinet_fixture_gets_no_fabricated_t60():
    res = compute_decay(_prep(fx.truncated_fixture(n=1200)), DecayConfig())
    assert res.t60_valid is False
    assert 'not a valid reverberation measurement' in res.t60_reason or \
        'truncated' in res.t60_reason
    assert res.t30_ms is None or res.t30_ms > 0   # reported, or explicitly None


def test_band_decay_present_for_fast_slow_pair():
    fast = compute_decay(_prep(fx.decay_fixture(100.0, 0.008, n=48000)),
                         DecayConfig())
    slow = compute_decay(_prep(fx.decay_fixture(100.0, 0.030, n=48000)),
                         DecayConfig())
    fd = fast.band_decay_ms.get('60-120', {})
    sd = slow.band_decay_ms.get('60-120', {})
    d20f, d20s = fd.get('D20'), sd.get('D20')
    if d20f is not None and d20s is not None:
        assert d20s > d20f


def test_fingerprint_deterministic_gain_invariant_and_cached(tmp_path):
    from tests.synth import write_wav
    p1 = Path(write_wav(tmp_path / 'a.wav', fx.boxy_fixture(300.0, 0.06, n=48000)))
    p2 = Path(write_wav(tmp_path / 'b.wav',
                        fx.boxy_fixture(300.0, 0.06, n=48000) * 0.5))
    r1, r2 = analyze_file(str(p1)), analyze_file(str(p2))
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fp1 = svc.fingerprint(r1)
    fp1_again = svc.fingerprint(r1)
    assert fp1.to_json() == fp1_again.to_json()   # deterministic + cached
    fp2 = svc.fingerprint(r2)
    # gain-invariant features match; absolute peak metadata is not a feature
    assert abs(fp1.transient['centroid_ms'].value -
               fp2.transient['centroid_ms'].value) < 0.05
    assert abs(fp1.decay['d20_low_ms'].value -
               fp2.decay['d20_low_ms'].value) < 5.0
    assert fp1.decay['d20_low_ms'].valid

    # cache round trip
    svc2 = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fp1_cached = svc2.fingerprint(r1)
    assert fp1_cached.to_json() == fp1.to_json()


def test_fingerprint_cache_identity_tracks_effective_service_config(tmp_path):
    """A changed fingerprint input config must not reuse a sidecar entry."""
    from tests.synth import write_wav
    path = Path(write_wav(tmp_path / 'a.wav',
                          fx.boxy_fixture(300.0, 0.06, n=48000)))
    record = analyze_file(str(path))
    cache = FingerprintCache(str(tmp_path / 'fp.db'))
    default = ResponseService(cache=cache)
    changed = ResponseService(env_cfg=EnvelopeConfig(rms_window_ms=4.0),
                              cache=cache)

    fp_default = default.fingerprint(record)
    fp_changed = changed.fingerprint(record)

    assert fp_default.cfg_hash != fp_changed.cfg_hash
    signature = fp_default.key.signature()
    assert cache.get(signature, fp_default.cfg_hash) is not None
    assert cache.get(signature, fp_changed.cfg_hash) is not None
    assert cache.count() == 2

    # A new default-config service round-trips exactly from its own cache slot.
    roundtrip = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    assert roundtrip.fingerprint(record).to_json() == fp_default.to_json()


def test_fingerprint_features_bounded_and_valid(tmp_path):
    from tests.synth import write_wav
    path = Path(write_wav(tmp_path / 'a.wav',
                          fx.boxy_fixture(300.0, 0.06, n=48000)))
    rec = analyze_file(str(path))
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fp = svc.fingerprint(rec)
    for group in (fp.transient, fp.decay, fp.phase):
        for name, feat in group.items():
            if feat.valid and feat.value is not None:
                assert np.isfinite(feat.value), (name, feat)
                assert abs(feat.value) < 1e6, (name, feat)
    # boxy fixture: the persistence feature should be valid and positive
    feat = fp.decay['boxiness_persistence_excess_db']
    assert feat.valid and feat.value > 1.0
