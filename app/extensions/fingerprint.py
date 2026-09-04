"""Response fingerprint assembly (WP-05).

Bounded scalar features with explicit validity, deterministically serializable,
cached in the SQLite sidecar keyed by file metadata + algorithm + config.
Gain-invariant where documented.
"""
from __future__ import annotations

import numpy as np

from ..core.analysis import AnalysisResult
from .channel_policy import valid_channel_aggregate
from .contracts import (ALGO_VERSION, AnalysisStatus, FeatureValue,
                        FingerprintCacheConfig, ResponseFingerprint)
from .envelope import compute_envelope
from .spectrogram import (DEFAULT_NEIGHBOR_BANDS, DEFAULT_PERSISTENCE_BAND,
                          compute_spectrogram)
from .service import ResponseService

# fp3: stereo channel policy plus an effective, configuration-sensitive cache
# identity.  Retained as a public policy marker for callers that need to label
# the calculation; it is not itself a cache key.
CFG_HASH = 'fp3-guitar-effective-config'


def effective_cfg_hash(service: ResponseService) -> str:
    """Return the deterministic persisted-cache identity for ``service``."""
    return FingerprintCacheConfig(
        policy=CFG_HASH,
        version=ALGO_VERSION,
        prep_cfg=service.prep_cfg,
        env_cfg=service.env_cfg,
        tf_cfg=service.tf_cfg,
        phase_cfg=service.phase_cfg,
        decay_cfg=service.decay_cfg,
    ).config_hash()


def compute_fingerprint(record: AnalysisResult, service: ResponseService,
                        ) -> ResponseFingerprint:
    cfg_hash = effective_cfg_hash(service)
    prepared = service.prepared(record)
    transient: dict[str, FeatureValue] = {}
    decay: dict[str, FeatureValue] = {}
    phase: dict[str, FeatureValue] = {}

    if prepared.status != AnalysisStatus.OK:
        empty = FeatureValue(None, False, f'analysis status: {prepared.status.value}')
        for group in (transient, decay, phase):
            group['unavailable'] = empty
        return ResponseFingerprint(key=prepared.key, version=ALGO_VERSION,
                                   cfg_hash=cfg_hash, transient=transient,
                                   decay=decay, phase=phase)

    # ---- transient (envelope) ---------------------------------------------
    env = compute_envelope(prepared, service.env_cfg)
    transient['onset_confidence'] = FeatureValue(
        float(prepared.onset_confidence), True)
    transient['time_to_peak_ms'] = FeatureValue(
        None if env.peak_time_ms is None else float(env.peak_time_ms),
        env.peak_time_ms is not None)
    transient['rise_time_ms'] = FeatureValue(
        None if env.rise_time_ms is None else float(env.rise_time_ms),
        bool(env.rise_valid), env.rise_reason)
    transient['early_energy_5ms'] = FeatureValue(
        None if env.early_energy_5ms is None else float(env.early_energy_5ms),
        env.early_energy_5ms is not None)
    transient['early_late_ratio'] = FeatureValue(
        None if env.early_late_ratio is None else float(env.early_late_ratio),
        env.early_late_ratio is not None)
    transient['centroid_ms'] = FeatureValue(
        None if env.centroid_ms is None else float(env.centroid_ms),
        env.centroid_ms is not None)
    transient['crest_factor'] = FeatureValue(
        None if env.crest_factor is None else float(env.crest_factor),
        env.crest_factor is not None)

    # ---- decay / resonance (CSD + spectrogram persistence) -----------------
    csd = service.csd(record)
    d20_name = 'D20_40-120_ms'
    decay['d20_low_ms'] = FeatureValue(
        _num(csd.metrics.get(d20_name)),
        bool(csd.metrics.get(d20_name + '_valid', False)),
        str(csd.metrics.get(d20_name + '_note', '')))
    slope = csd.metrics.get('slope_40-120_db_per_s')
    decay['low_band_slope_db_s'] = FeatureValue(
        _num(slope), slope is not None,
        str(csd.metrics.get('slope_40-120_note', '')))
    ratio = csd.metrics.get('low_late_early_ratio_db')
    decay['low_late_early_db'] = FeatureValue(_num(ratio), ratio is not None)

    spec = compute_spectrogram(prepared, service.tf_cfg,
                               persistence_band=DEFAULT_PERSISTENCE_BAND,
                               neighbor_bands=DEFAULT_NEIGHBOR_BANDS)
    m = spec.metrics
    decay['boxiness_persistence_excess_db'] = FeatureValue(
        _num(m.get('persistence_excess_db')),
        bool(m.get('persistence_valid', False)),
        str(m.get('persistence_note', '')))
    decay['boxiness_ridge_hz'] = FeatureValue(
        _num(m.get('persistence_ridge_hz')),
        bool(m.get('persistence_valid', False)))
    decay['boxiness_q'] = FeatureValue(_num(m.get('persistence_q')),
                                       m.get('persistence_q') is not None)

    # ---- phase ---------------------------------------------------------------
    # Channel policy: group-delay scalars aggregate ONLY valid channel evidence
    # (B11 per-channel masks) — a silent or anti-phase channel never corrupts
    # another channel's valid bins. The note carries policy provenance
    # (contributing channels + valid bin count); it is JSON-serialized with the
    # feature but not surfaced by the Summary UI (notes show only when invalid).
    ph = service.phase(record)
    gd = ph.group_delay_ms if ph.group_delay_ms is not None else np.empty((0, 0))
    valid = (ph.valid_mask & np.isfinite(gd)
             if gd.size and ph.valid_mask is not None
             else np.zeros(gd.shape, dtype=bool))
    med, n_valid, ch_used = valid_channel_aggregate(gd, valid, agg='median')
    lo, _, _ = valid_channel_aggregate(gd, valid, agg='p25')
    hi, _, _ = valid_channel_aggregate(gd, valid, agg='p75')
    if n_valid:
        # compact channel list: (0,), (0,1) — no spaces, stable in JSON notes
        provenance = f'valid channels={str(ch_used).replace(" ", "")} bins={n_valid}'
        phase['gd_median_ms'] = FeatureValue(med, True, provenance)
        phase['gd_spread_ms'] = FeatureValue(hi - lo, True, provenance)
        phase['gd_valid_coverage'] = FeatureValue(float(ph.coverage), True)
    else:
        phase['gd_median_ms'] = FeatureValue(None, False, 'no valid bins')
        phase['gd_spread_ms'] = FeatureValue(None, False, 'no valid bins')
        phase['gd_valid_coverage'] = FeatureValue(float(ph.coverage), True)

    return ResponseFingerprint(key=prepared.key, version=ALGO_VERSION,
                               cfg_hash=cfg_hash, transient=transient,
                               decay=decay, phase=phase)


def _num(v):
    return None if v is None else float(v)
