"""Response-aware search: tone first, response second (WP-06).

Stage 1 keeps the legacy `score_curve` ranking untouched. Stage 2 applies
explicit constraints and normalized weighted losses over scalar fingerprints.
Missing metrics follow an explicit policy: 'exclude' (drop the component and
renormalize weights) or 'reject' (the candidate cannot rank). Legacy
`AnalysisResult.score` is never mutated in advanced mode.
"""
from __future__ import annotations

import numpy as np

from ..core.analysis import AnalysisResult
from ..core.matching import score_curve
from .contracts import (FeatureValue, ResponseFingerprint, ScoreBreakdown,
                        ScoreComponent, RankedCandidate)

POLICIES = ('exclude', 'reject')


def stage1_shortlist(records: list[AnalysisResult], target_curve: np.ndarray,
                     lo: float = 80.0, hi: float = 8000.0,
                     max_tone_db: float | None = None,
                     top_k: int | None = None
                     ) -> list[tuple[AnalysisResult, float]]:
    """Stage 1: legacy tone ranking (unchanged math), optional cutoff."""
    scored = [(r, score_curve(r.curve_db, target_curve, lo, hi))
              for r in records]
    scored.sort(key=lambda t: t[1])
    if max_tone_db is not None:
        scored = [t for t in scored if t[1] <= max_tone_db]
    if top_k is not None:
        scored = scored[:top_k]
    return scored


def _component(name: str, feat: FeatureValue | None, target: float,
               scale_db: float, weight: float, policy: str,
               constraint_max: float | None = None) -> ScoreComponent:
    """Build one normalized loss component from a fingerprint feature.

    norm_loss = clamp(|value - target| / scale, 0, 1). When the feature is
    invalid: 'exclude' -> weight renormalized away by the caller; 'reject' ->
    the candidate is dropped with a reason.
    """
    if feat is None or not feat.valid or feat.value is None:
        if policy == 'reject':
            return ScoreComponent(name=name, raw_value=None, norm_loss=1.0,
                                  weight=weight, contribution=np.inf,
                                  valid=False,
                                  note=feat.note if feat else 'missing')
        return ScoreComponent(name=name, raw_value=None, norm_loss=0.0,
                              weight=weight, contribution=0.0, valid=False,
                              note=feat.note if feat else 'missing')
    loss = min(abs(feat.value - target) / max(scale_db, 1e-9), 1.0)
    if constraint_max is not None and feat.value > constraint_max:
        loss = 1.0
    return ScoreComponent(name=name, raw_value=float(feat.value),
                          norm_loss=float(loss), weight=float(weight),
                          contribution=float(loss * weight), valid=True,
                          note='')


def rank_by_response(records: list[AnalysisResult], fingerprints: dict[str, ResponseFingerprint],
                     service: ResponseServiceLike, target_curve: np.ndarray,
                     weights: dict[str, float] | None = None,
                     constraints: dict[str, float] | None = None,
                     targets: dict[str, float] | None = None,
                     lo: float = 80.0, hi: float = 8000.0,
                     max_tone_db: float = 6.0,
                     policy: str = 'exclude'
                     ) -> list[RankedCandidate]:
    """Stage 2 + 3: response-aware ranking with an explainable breakdown.

    Component keys (target, scale) — targets come from `targets` when given,
    otherwise from library medians:
      tone          legacy dB score  (target 0, scale 3 dB)  - always weighted
      d20           low-end D20 ms   (scale 40 ms)
      attack        time-to-peak ms  (scale 2 ms)
      boxiness      persistence dB   (target 0, scale 6 dB)
      gd_spread     group-delay IQR  (target 0, scale 2 ms)
    """
    if policy not in POLICIES:
        raise ValueError(f'unknown policy {policy!r}')
    weights = weights or {'tone': 1.0, 'd20': 0.0, 'attack': 0.0,
                          'boxiness': 0.0, 'gd_spread': 0.0}
    constraints = constraints or {}
    targets = targets or {}
    for key, feat_name in (('d20', 'd20_low_ms'),
                           ('attack', 'time_to_peak_ms'),
                           ('boxiness', 'boxiness_persistence_excess_db'),
                           ('gd_spread', 'gd_spread_ms')):
        if key in targets:
            continue
        vals = []
        for fp in fingerprints.values():
            feat = fp.all_features().get(feat_name)
            if feat and feat.valid and feat.value is not None:
                vals.append(feat.value)
        targets[key] = float(np.median(vals)) if vals else 0.0

    candidates: list[RankedCandidate] = []
    for rec, tone_db in stage1_shortlist(records, target_curve, lo, hi,
                                         max_tone_db=max_tone_db):
        fp = fingerprints.get(rec.path)
        if fp is None:
            candidates.append(RankedCandidate(record=rec, fingerprint=None,
                                              breakdown=None, excluded=True,
                                              reason='no fingerprint'))
            continue
        feats = fp.all_features()
        comps: list[ScoreComponent] = []
        reasons: list[str] = []
        rejected = False

        comps.append(ScoreComponent(
            name='tone', raw_value=float(tone_db),
            norm_loss=min(tone_db / 3.0, 1.0), weight=float(weights.get('tone', 1.0)),
            contribution=min(tone_db / 3.0, 1.0) * float(weights.get('tone', 1.0)),
            valid=True))
        if 'max_tone_db' in constraints and tone_db > constraints['max_tone_db']:
            reasons.append(f'tone {tone_db:.2f} dB > {constraints["max_tone_db"]}')

        spec = (
            ('d20', ('decay', 'd20_low_ms'), targets['d20'], 40.0,
             constraints.get('max_d20_ms')),
            ('attack', ('transient', 'time_to_peak_ms'), targets['attack'], 2.0,
             constraints.get('max_attack_ms')),
            ('boxiness', ('decay', 'boxiness_persistence_excess_db'),
             targets['boxiness'], 6.0, constraints.get('max_boxiness_db')),
            ('gd_spread', ('phase', 'gd_spread_ms'), targets['gd_spread'], 2.0,
             constraints.get('max_gd_spread_ms')),
        )
        for key, path, tgt, scale, cons in spec:
            w = float(weights.get(key, 0.0))
            if w <= 0.0 and cons is None:
                continue
            feat = feats.get(path[1])
            comp = _component(key, feat, tgt, scale, w, policy, cons)
            if comp.valid and cons is not None and feat.value > cons:
                reasons.append(f'{key} {feat.value:.2f} > {cons}')
            if not comp.valid and policy == 'reject' and w > 0.0:
                rejected = True
                reasons.append(f'{key} invalid: {comp.note}')
            comps.append(comp)

        active = [c for c in comps if c.valid and c.weight > 0]
        wsum = sum(c.weight for c in active)
        total = sum(c.contribution for c in active) / wsum if wsum > 0 else 1.0
        excluded = rejected or bool(reasons)
        reason = '; '.join(reasons) if reasons else ''
        candidates.append(RankedCandidate(record=rec, fingerprint=fp,
                                          breakdown=ScoreBreakdown(
                                              total=total,
                                              components=tuple(comps)),
                                          excluded=excluded, reason=reason))

    eligible = [c for c in candidates if not c.excluded]
    eligible.sort(key=lambda c: c.breakdown.total)
    others = [c for c in candidates if c.excluded]
    for i, c in enumerate(eligible):
        candidates[candidates.index(c)] = RankedCandidate(
            record=c.record, fingerprint=c.fingerprint, breakdown=c.breakdown,
            rank=i + 1, excluded=False, reason=c.reason)
    out = eligible + others
    return out


def pair_search(records: list[AnalysisResult], anchor: AnalysisResult,
                fingerprints: dict[str, ResponseFingerprint], service,
                max_tone_db: float = 3.0, top_k: int = 5
                ) -> list[RankedCandidate]:
    """Stage 4: best blend-compatible partner for `anchor` (plan section 9).

    Candidates within a legacy tone threshold of the ANCHOR's curve are ranked
    by predicted aligned blend cancellation risk. Heavier than scalar ranking:
    a pair analysis per candidate — keep the shortlist small.
    """
    from .pair_compare import compare_pair, predict_blend
    from .contracts import PairComparisonConfig
    anchor_curve = anchor.curve_db
    shortlist = stage1_shortlist(records, anchor_curve, max_tone_db=max_tone_db,
                                 top_k=top_k + 1)
    out: list[RankedCandidate] = []
    cfg = PairComparisonConfig()
    for rec, tone_db in shortlist:
        if rec.path == anchor.path:
            continue
        try:
            pair = compare_pair(service.prepared(anchor), service.prepared(rec), cfg)
            blend = predict_blend(service.prepared(anchor), service.prepared(rec),
                                  cfg, alignment='suggested')
        except Exception as exc:
            out.append(RankedCandidate(record=rec, fingerprint=None,
                                       breakdown=None, excluded=True,
                                       reason=f'pair analysis failed: {exc}'))
            continue
        risk = blend.worst_cancellation_db
        valid = risk is not None
        loss = min((risk or 0.0) / 24.0, 1.0)
        comp = ScoreComponent(name='blend_risk', raw_value=risk,
                              norm_loss=loss, weight=1.0,
                              contribution=loss, valid=valid,
                              note='' if valid else 'no valid bins')
        out.append(RankedCandidate(
            record=rec, fingerprint=fingerprints.get(rec.path),
            breakdown=ScoreBreakdown(total=loss, components=(comp,)),
            excluded=not valid,
            reason='' if valid else 'blend prediction had no valid bins'))
    out.sort(key=lambda c: (c.excluded, c.breakdown.total if c.breakdown else 9e9))
    for i, c in enumerate(out):
        if not c.excluded:
            out[i] = RankedCandidate(record=c.record, fingerprint=c.fingerprint,
                                     breakdown=c.breakdown, rank=i + 1,
                                     excluded=False, reason=c.reason)
    return out[:top_k]


class ResponseServiceLike:
    """Typing aid for the service surface used by matching."""
