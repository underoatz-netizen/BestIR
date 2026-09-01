"""Response fingerprint assembly (WP-05).

Bounded scalar features with explicit validity, deterministically serializable,
cached in the SQLite sidecar keyed by file metadata + algorithm + config.
Gain-invariant where documented.
"""
from __future__ import annotations

import numpy as np

from ..core.analysis import AnalysisResult
from .contracts import (ALGO_VERSION, AnalysisStatus, FeatureValue,
                        ResponseFingerprint)
from .envelope import compute_envelope
from .spectrogram import (DEFAULT_NEIGHBOR_BANDS, DEFAULT_PERSISTENCE_BAND,
                          compute_spectrogram)
from .service import ResponseService

CFG_HASH = 'fp1-guitar-default'


def compute_fingerprint(record: AnalysisResult, service: ResponseService,
                        ) -> ResponseFingerprint:
    prepared = service.prepared(record)
    transient: dict[str, FeatureValue] = {}
    decay: dict[str, FeatureValue] = {}
    phase: dict[str, FeatureValue] = {}

    if prepared.status != AnalysisStatus.OK:
        empty = FeatureValue(None, False, f'analysis status: {prepared.status.value}')
        for group in (transient, decay, phase):
            group['unavailable'] = empty
        return ResponseFingerprint(key=prepared.key, version=ALGO_VERSION,
                                   cfg_hash=CFG_HASH, transient=transient,
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
    ph = service.phase(record)
    gd = ph.group_delay_ms[:, 0] if ph.group_delay_ms is not None else np.array([])
    valid = (ph.valid_mask[:, 0] & np.isfinite(gd) if len(gd)
             else np.zeros(0, bool))
    if valid.any():
        med = float(np.median(gd[valid]))
        spread = float(np.percentile(gd[valid], 75) - np.percentile(gd[valid], 25))
        phase['gd_median_ms'] = FeatureValue(med, True)
        phase['gd_spread_ms'] = FeatureValue(spread, True)
        phase['gd_valid_coverage'] = FeatureValue(float(ph.coverage), True)
    else:
        phase['gd_median_ms'] = FeatureValue(None, False, 'no valid bins')
        phase['gd_spread_ms'] = FeatureValue(None, False, 'no valid bins')
        phase['gd_valid_coverage'] = FeatureValue(float(ph.coverage), True)

    return ResponseFingerprint(key=prepared.key, version=ALGO_VERSION,
                               cfg_hash=CFG_HASH, transient=transient,
                               decay=decay, phase=phase)


def _num(v):
    return None if v is None else float(v)
