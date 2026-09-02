"""WP-06 gates: response-aware matching and pair search."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.analysis import analyze_file
from app.core.matching import score_curve
from app.extensions.advanced_matching import (pair_search, rank_by_response,
                                              response_search,
                                              stage1_shortlist)
from app.extensions.cache import FingerprintCache
from app.extensions.contracts import FeatureValue, ResponseFingerprint, SourceKey
from app.extensions.service import ResponseService
from tests.extensions import fixtures as fx

ANCHORS = [20, 60, 120, 350, 1000, 3500, 8000, 20000]


def _mk(tmp_path, name, anchors, seed):
    from tests.synth import synth_ir, write_wav
    ir = synth_ir(sr=48000, n=48000, anchors_db=anchors, seed=seed)
    path = write_wav(tmp_path / name, ir)
    return analyze_file(str(path))


def _tight_vs_boomy(tmp_path):
    """Two tone-identical IRs: one fast/tight low end, one slow/boomy ring."""
    from tests.synth import synth_ir, write_wav
    base = synth_ir(sr=48000, n=48000, anchors_db=[0, 1, 0, -1, 0, 1, 0, 1],
                    seed=1)
    t = np.arange(48000) / 48000
    ring = np.zeros(48000)
    ring[96:] = 0.4 * np.cos(2 * np.pi * 100.0 * t[:48000 - 96]) * \
        np.exp(-t[:48000 - 96] / 0.06)     # slow 100 Hz ring = boomy tail
    tight_ring = np.zeros(48000)
    tight_ring[96:] = 0.4 * np.cos(2 * np.pi * 100.0 * t[:48000 - 96]) * \
        np.exp(-t[:48000 - 96] / 0.004)    # same band, tiny tau = tight
    tight = base + tight_ring
    boomy = base + ring
    pa = write_wav(tmp_path / 'tight.wav', tight / (np.max(np.abs(tight)) + 1e-9))
    pb = write_wav(tmp_path / 'boomy.wav', boomy /
                   (np.max(np.abs(boomy)) + 1e-9))
    return analyze_file(str(pa)), analyze_file(str(pb))


def test_stage1_reproduces_legacy_score(tmp_path):
    a, b = _tight_vs_boomy(tmp_path)
    target = np.zeros(96)
    short = stage1_shortlist([a, b], target)
    for rec, s in short:
        assert s == score_curve(rec.curve_db, target, 80.0, 8000.0)


def test_stage2_never_promotes_outside_tone_constraint(tmp_path):
    tight, boomy = _tight_vs_boomy(tmp_path)
    far = _mk(tmp_path, 'far.wav', [6, 4, 2, 0, -2, -4, -6, -8], seed=9)
    records = [tight, boomy, far]
    target = tight.curve_db    # tone target = the tight IR itself
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fps = {r.path: svc.fingerprint(r) for r in records}
    out = rank_by_response(records, fps, svc, target,
                           weights={'tone': 1.0, 'd20': 1.0},
                           constraints={'max_tone_db': 2.0})
    ranked_paths = [c.record.path for c in out if not c.excluded]
    assert far.path not in ranked_paths
    assert tight.path in ranked_paths


def test_tight_ranks_above_boomy_for_tightness_weight(tmp_path):
    tight, boomy = _tight_vs_boomy(tmp_path)
    records = [tight, boomy]
    target = tight.curve_db
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fps = {r.path: svc.fingerprint(r) for r in records}
    out = rank_by_response(records, fps, svc, target,
                           weights={'tone': 0.0, 'd20': 1.0},
                           targets={'d20': 15.0},      # user wants a tight low end
                           policy='exclude')
    top = [c for c in out if not c.excluded]
    assert top, [c.reason for c in out]
    assert top[0].record.path == tight.path, \
        (top[0].breakdown.explain(), top[0].record.path)


def test_b08_ranking_follows_desired_targets_not_library_median():
    """B08 gate: synthetic candidates rank by the DESIRED response target, not
    by the library median, and the caller's targets dict is never mutated."""
    from types import SimpleNamespace

    from app.extensions.contracts import (FeatureValue, ResponseFingerprint,
                                          SourceKey)

    def record(name):
        return SimpleNamespace(path=str(name), curve_db=np.zeros(96),
                               flatness_db=1.0)

    def fp(name, d20_ms):
        return ResponseFingerprint(
            key=SourceKey(str(name), 0, 0, 48000, 1), version='test',
            cfg_hash='test', transient={},
            decay={'d20_low_ms': FeatureValue(float(d20_ms), True, '')},
            phase={})

    r_lo, r_mid, r_hi = record('lo'), record('mid'), record('hi')
    d20_values = {'lo': 10.0, 'mid': 50.0, 'hi': 90.0}
    records = [r_lo, r_mid, r_hi]
    fps = {r.path: fp(r.path, v) for r, v in zip(records, d20_values.values())}
    assert float(np.median(list(d20_values.values()))) == 50.0   # library median
    weights = {'tone': 0.0, 'd20': 1.0}    # only d20 decides the order

    def winner(desired_d20):
        targets = {'d20': desired_d20}
        out = rank_by_response(records, fps, None, np.zeros(96),
                               weights=weights, targets=targets,
                               policy='exclude')
        eligible = [c for c in out if not c.excluded]
        assert eligible, [c.reason for c in out]
        assert targets == {'d20': desired_d20}, \
            'rank_by_response mutated the caller targets dict'
        return eligible[0].record.path

    # desired 10 ms wins despite the library median being 50 ms
    assert winner(10.0) == r_lo.path
    # same library, opposite desired target -> opposite winner
    assert winner(90.0) == r_hi.path


def test_missing_data_reject_policy(tmp_path):
    tight, boomy = _tight_vs_boomy(tmp_path)
    records = [tight, boomy]
    target = tight.curve_db
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fps = {r.path: svc.fingerprint(r) for r in records}
    # drop phase data for one candidate -> 'reject' removes it from ranking
    broken = ResponseFingerprint(
        key=fps[tight.path].key, version=fps[tight.path].version,
        cfg_hash=fps[tight.path].cfg_hash,
        transient=fps[tight.path].transient, decay=fps[tight.path].decay,
        phase={'gd_spread_ms': FeatureValue(None, False, 'no valid bins')})
    fps2 = dict(fps)
    fps2[tight.path] = broken
    out = rank_by_response(records, fps2, svc, target,
                           weights={'tone': 0.0, 'gd_spread': 1.0},
                           policy='reject')
    assert all(c.record.path != tight.path or c.excluded for c in out)


def test_score_breakdown_explains_and_never_mutates_legacy(tmp_path):
    tight, boomy = _tight_vs_boomy(tmp_path)
    records = [tight, boomy]
    target = tight.curve_db
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fps = {r.path: svc.fingerprint(r) for r in records}
    before = {r.path: (r.curve_db.copy(), r.flatness_db) for r in records}
    out = rank_by_response(records, fps, svc, target,
                           weights={'tone': 1.0, 'boxiness': 1.0})
    assert all(c.breakdown is not None for c in out if not c.excluded)
    text = out[0].breakdown.explain()
    assert 'tone' in text and 'boxiness' in text
    for r in records:
        assert np.array_equal(r.curve_db, before[r.path][0])
        assert r.flatness_db == before[r.path][1]


def test_pair_search_prefers_phase_compatible_partner(tmp_path):
    a = fx.boxy_fixture(250.0, 0.02, n=24000)
    same = a.copy()
    inverted = -a
    from app.core.analysis import analyze_data
    from tests.synth import write_wav
    pa = analyze_file(str(Path(write_wav(tmp_path / 'a.wav', a))))
    psame = analyze_file(str(Path(write_wav(tmp_path / 'same.wav', same))))
    pinv = analyze_file(str(Path(write_wav(tmp_path / 'inv.wav', inverted))))
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))
    fps = {r.path: svc.fingerprint(r) for r in (pa, psame, pinv)}
    out = pair_search([psame, pinv], pa, fps, svc, max_tone_db=6.0)
    assert out, 'pair search should return candidates'
    best = out[0]
    assert best.record.path == psame.path, \
        (best.record.path, best.breakdown.explain() if best.breakdown else None)


def _fp_spy(records, service):
    """Fingerprint-getter that records which records were requested, so a test
    can prove the shared pipeline fingerprints only the stage-1 shortlist."""
    requested = []

    def get(record):
        requested.append(record.path)
        return service.fingerprint(record)

    return get, requested


def test_b16_shared_pipeline_shortlists_before_fingerprinting(tmp_path):
    """B16 gate: response_search fingerprints ONLY the stage-1 tone shortlist
    (bounded, identical to both UI entry points) — never the full library."""
    tight, boomy = _tight_vs_boomy(tmp_path)
    far = _mk(tmp_path, 'far.wav', [6, 4, 2, 0, -2, -4, -6, -8], seed=9)
    records = [tight, boomy, far]
    target = tight.curve_db
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))

    get, requested = _fp_spy(records, svc)
    out = response_search(records, svc, target, fingerprints_get=get,
                          weights={'tone': 1.0, 'd20': 1.0},
                          constraints={'max_tone_db': 3.0},
                          policy='exclude', top_k=2)
    assert requested, 'pipeline never requested fingerprints'
    assert far.path not in requested, \
        'off-shortlist record was fingerprinted by the shared pipeline'
    ranked_paths = [c.record.path for c in out if not c.excluded]
    assert tight.path in ranked_paths
    assert far.path not in ranked_paths   # tone constraint excludes far


def test_b16_shared_pipeline_equals_explicit_two_stage(tmp_path):
    """B16 gate: response_search is exactly stage1_shortlist -> fingerprint ->
    rank_by_response — the same math a caller would write by hand, so the two
    UI entry points cannot drift from each other or from the raw functions."""
    tight, boomy = _tight_vs_boomy(tmp_path)
    far = _mk(tmp_path, 'far.wav', [6, 4, 2, 0, -2, -4, -6, -8], seed=9)
    records = [tight, boomy, far]
    target = tight.curve_db
    svc = ResponseService(cache=FingerprintCache(str(tmp_path / 'fp.db')))

    request = {'weights': {'tone': 1.0, 'd20': 1.0, 'boxiness': 1.0},
               'constraints': {'max_tone_db': 3.0},
               'targets': {'d20': 15.0, 'boxiness': 0.0},
               'policy': 'exclude'}
    shared = response_search(
        records, svc, target, fingerprints_get=svc.fingerprint,
        weights=request['weights'], constraints=request['constraints'],
        targets=request['targets'], policy=request['policy'])

    max_tone = request['constraints'].get('max_tone_db', 6.0)
    short = stage1_shortlist(records, target, max_tone_db=max_tone, top_k=40)
    short_records = [r for r, _ in short]
    fps = {r.path: svc.fingerprint(r) for r in short_records}
    manual = rank_by_response(short_records, fps, svc, target,
                              weights=request['weights'],
                              constraints=request['constraints'],
                              targets=request['targets'],
                              policy=request['policy'],
                              max_tone_db=max_tone)

    assert len(shared) == len(manual)
    for c_s, c_m in zip(shared, manual):
        assert c_s.record.path == c_m.record.path
        assert c_s.excluded == c_m.excluded
        assert c_s.reason == c_m.reason
        if c_s.breakdown is not None:
            assert c_s.breakdown.total == c_m.breakdown.total
            assert ([x.name for x in c_s.breakdown.components]
                    == [x.name for x in c_m.breakdown.components])
            assert ([(x.raw_value, x.norm_loss) for x in c_s.breakdown.components]
                    == [(x.raw_value, x.norm_loss) for x in c_m.breakdown.components])
