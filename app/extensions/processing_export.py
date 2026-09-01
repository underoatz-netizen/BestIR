"""Processed-copy export: aligned B, blend WAV, provenance report (WP-08).

All writes are collision-safe (unique suffix) and atomic (temp file +
os.replace). Source files are never modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import soundfile as sf

from .contracts import (AnalysisStatus, BlendPrediction, FeatureValue,
                        IRProcessingConfig, PairComparisonResult, PreparedIR,
                        ProcessingReport, ResponseFingerprint)
from .pair_preparation import prepare_pair
from .processing import apply_alignment, blend_sum, fractional_shift


def unique_dest(dest_dir: str, name: str) -> Path:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    dest = Path(dest_dir) / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(2, 1000):
        dest = Path(dest_dir) / f'{stem} ({i}){suffix}'
        if not dest.exists():
            return dest
    raise RuntimeError(f'no free filename for {name}')


def _atomic_write_wav(path: Path, data: np.ndarray, sr: int, subtype: str) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    if data.shape[1] == 1:
        sf.write(str(tmp), data[:, 0], sr, subtype=subtype, format='WAV')
    else:
        sf.write(str(tmp), data, sr, subtype=subtype, format='WAV')
    os.replace(tmp, path)


def _source_name(prepared: PreparedIR, suffix: str) -> str:
    name = Path(prepared.key.path).stem
    return f'{name} {suffix}.wav'


def export_processed(prepared: PreparedIR, cfg: IRProcessingConfig,
                     dest_dir: str, suffix: str = 'aligned') -> ProcessingReport:
    """Write an aligned/polarity-corrected copy of the prepared IR."""
    data, warnings = apply_alignment(prepared, cfg)
    dest = unique_dest(dest_dir, _source_name(prepared, suffix))
    _atomic_write_wav(dest, data, prepared.sample_rate, cfg.output_subtype)
    applied = {
        'delay_samples advanced': cfg.delay_samples,
        'polarity': cfg.polarity,
        'output_subtype': cfg.output_subtype,
        'channels': int(data.shape[1]),
        'sample_rate_hz': prepared.sample_rate,
        'length_samples': int(data.shape[0]),
    }
    if cfg.normalize_peak_dbfs is not None:
        applied['normalize_peak_dbfs'] = cfg.normalize_peak_dbfs
    return ProcessingReport(source_key=prepared.key, output_path=str(dest),
                            applied=applied, warnings=tuple(warnings))


def export_pair_aligned_b(a: PreparedIR, b: PreparedIR,
                          pair: PairComparisonResult, dest_dir: str,
                          cfg: IRProcessingConfig | None = None,
                          suffix: str = 'aligned') -> ProcessingReport:
    """Write B aligned to A on the pair's common (A) analysis rate.

    The measured ``pair.delay_samples`` is expressed in the pair's analysis
    rate (A's rate after ``prepare_pair``).  Applying it to B's *native* rate
    would change the physical time shift for mixed-rate sources, so this
    helper resamples B to the common rate first (via ``prepare_pair``) and
    then applies the polarity/delay there.  The full B buffer is retained and
    the output is zero-padded to length + |delay| so the tail is never
    truncated by either shift direction.
    """
    prepared = prepare_pair(a, b)
    if prepared.status != AnalysisStatus.OK:
        raise ValueError(prepared.reason or
                         'both IRs must analyze cleanly before aligned-B export')
    subtype = cfg.output_subtype if cfg else 'PCM_24'
    advance = float(pair.delay_samples)
    s = pair.polarity if pair.polarity != 0 else 1
    data_b = np.array(prepared.data_b, dtype=np.float64, copy=True)
    if s == -1:
        data_b = -data_b
    data_b = fractional_shift(data_b, advance,
                              output_frames=len(data_b) + int(np.ceil(abs(advance))))
    warnings = list(prepared.warnings)
    if cfg is not None and cfg.normalize_peak_dbfs is not None:
        peak = float(np.max(np.abs(data_b)))
        if peak > 0:
            target = 10 ** (cfg.normalize_peak_dbfs / 20.0)
            data_b = data_b * (target / peak)
        else:
            warnings.append('silent IR: normalization skipped')

    dest = unique_dest(dest_dir, _source_name(b, suffix))
    _atomic_write_wav(dest, data_b, prepared.sample_rate, subtype)
    applied = {
        'delay_samples advanced (B, analysis rate)': advance,
        'delay_ms advanced (B)': pair.delay_ms,
        'polarity (B)': s,
        'alignment': 'measured (onset + cross-correlation, prepare_pair)',
        'output_subtype': subtype,
        'channels': int(data_b.shape[1]),
        'source_sample_rate_a_hz': prepared.source_sample_rate_a,
        'source_sample_rate_b_hz': prepared.source_sample_rate_b,
        'analysis_output_sample_rate_hz': prepared.sample_rate,
        'sample_rate_hz': prepared.sample_rate,
        'length_samples': int(data_b.shape[0]),
    }
    if cfg is not None and cfg.normalize_peak_dbfs is not None:
        applied['normalize_peak_dbfs'] = cfg.normalize_peak_dbfs
    return ProcessingReport(source_key=b.key, output_path=str(dest),
                            applied=applied, warnings=tuple(warnings))


def export_blend(a: PreparedIR, b: PreparedIR, pair: PairComparisonResult,
                 ratio_b: float, dest_dir: str,
                 cfg: IRProcessingConfig | None = None) -> ProcessingReport:
    """Write the aligned A+B blend as a new IR."""
    subtype = (cfg.output_subtype if cfg else 'PCM_24')
    mix, sr, warnings = blend_sum(a, b, pair, ratio_b, cfg)
    name_a = Path(a.key.path).stem
    name_b = Path(b.key.path).stem
    dest = unique_dest(dest_dir, f'{name_a} + {name_b} ({int(ratio_b * 100)}pct B).wav')
    _atomic_write_wav(dest, mix, sr, subtype)
    applied = {
        'blend_ratio_b': ratio_b,
        'delay_samples advanced (B)': pair.delay_samples,
        'onset_delay_samples (B relative to A)': pair.onset_delay_samples,
        'residual_delay_samples (after onset alignment)': pair.residual_delay_samples,
        'total_applied_delay_samples (B advanced)': pair.delay_samples,
        'polarity (B)': pair.polarity,
        'alignment': 'measured (onset + cross-correlation)',
        'output_subtype': subtype,
        'source_sample_rate_a_hz': a.sample_rate,
        'source_sample_rate_b_hz': b.sample_rate,
        'analysis_output_sample_rate_hz': sr,
        'sample_rate_hz': sr,
        'length_samples': int(mix.shape[0]),
    }
    return ProcessingReport(source_key=a.key, output_path=str(dest),
                            applied=applied, warnings=tuple(warnings))


def export_pair_report(pair: PairComparisonResult, blend: BlendPrediction | None,
                       fp_a: ResponseFingerprint | None,
                       fp_b: ResponseFingerprint | None,
                       dest_dir: str, name: str = 'pair_report.json'
                       ) -> ProcessingReport:
    """Write the measurement provenance report (plan section 11.6)."""
    dest = unique_dest(dest_dir, name)
    doc = {
        'algo_version': pair.cfg.version,
        'units': {'delay_ms': 'ms', 'delay_samples': 'samples',
                  'phase': 'radians', 'magnitudes': 'dB',
                  'cancellation': 'dB below power-sum expectation'},
        'pair': {
            'source_a': pair.key_a.path,
            'source_b': pair.key_b.path,
            'signature_a': pair.key_a.signature(),
            'signature_b': pair.key_b.signature(),
            'delay_ms': pair.delay_ms,
            'delay_samples': pair.delay_samples,
            'onset_delay_samples': pair.onset_delay_samples,
            'residual_delay_samples': pair.residual_delay_samples,
            'total_applied_delay_samples': pair.delay_samples,
            'polarity': pair.polarity,
            'source_sample_rate_a_hz': (
                pair.source_sample_rate_a or pair.key_a.sample_rate),
            'source_sample_rate_b_hz': (
                pair.source_sample_rate_b or pair.key_b.sample_rate),
            'analysis_sample_rate_hz': (
                pair.analysis_sample_rate or pair.key_a.sample_rate),
            'correlation_confidence': pair.correlation_confidence,
            'phase_diff_weighted_rms_deg': pair.phase_diff_weighted_rms_deg,
            'valid_fraction': pair.valid_fraction,
        },
        'blend': None if blend is None else {
            'ratios': list(blend.ratios),
            'alignment': blend.alignment,
            'cancellation_reference_ratio_b': (
                float(min(blend.ratios, key=lambda ratio: abs(ratio - 0.5)))
                if blend.ratios else None),
            'worst_cancellation_db': blend.worst_cancellation_db,
            'worst_cancellation_freq_hz': blend.worst_cancellation_freq,
            'notch_freqs_hz': list(blend.notch_freqs),
            'rms_deviation_db': blend.rms_deviation_db,
            'phase_compat_score': blend.phase_compat_score,
            'sensitivity_pm1_sample': blend.sensitivity,
            'risk_by_ratio': {
                str(ratio): {
                    'worst_cancellation_db': risk.worst_cancellation_db,
                    'worst_cancellation_freq_hz': risk.worst_cancellation_freq,
                    'notch_freqs_hz': list(risk.notch_freqs),
                    'sensitivity_pm1_sample': dict(risk.sensitivity),
                }
                for ratio, risk in blend.risk_by_ratio.items()
            },
            'verified_rms_db': blend.verified_rms_db,
        },
        'fingerprint_a': None if fp_a is None else _fp_doc(fp_a),
        'fingerprint_b': None if fp_b is None else _fp_doc(fp_b),
        'warnings': list(pair.warnings) + list(blend.warnings if blend else []),
    }
    tmp = dest.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    os.replace(tmp, dest)
    return ProcessingReport(source_key=pair.key_a, output_path=str(dest),
                            applied={'report': 'pair provenance'},
                            warnings=tuple(pair.warnings))


def _fp_doc(fp: ResponseFingerprint) -> dict:
    def feat(f: FeatureValue) -> dict:
        return {'value': f.value, 'valid': f.valid, 'note': f.note}
    return {
        'signature': fp.key.signature(),
        'version': fp.version,
        'cfg_hash': fp.cfg_hash,
        'transient': {k: feat(v) for k, v in fp.transient.items()},
        'decay': {k: feat(v) for k, v in fp.decay.items()},
        'phase': {k: feat(v) for k, v in fp.phase.items()},
    }

