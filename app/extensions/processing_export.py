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

from .contracts import (BlendPrediction, FeatureValue, IRProcessingConfig,
                        PairComparisonResult, PreparedIR, ProcessingReport,
                        ResponseFingerprint)
from .processing import apply_alignment, blend_sum


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


def export_blend(a: PreparedIR, b: PreparedIR, pair: PairComparisonResult,
                 ratio_b: float, dest_dir: str,
                 cfg: IRProcessingConfig | None = None) -> ProcessingReport:
    """Write the aligned A+B blend as a new IR."""
    subtype = (cfg.output_subtype if cfg else 'PCM_24')
    mix, sr, warnings = blend_sum(a, b, pair, ratio_b)
    name_a = Path(a.key.path).stem
    name_b = Path(b.key.path).stem
    dest = unique_dest(dest_dir, f'{name_a} + {name_b} ({int(ratio_b * 100)}pct B).wav')
    _atomic_write_wav(dest, mix, sr, subtype)
    applied = {
        'blend_ratio_b': ratio_b,
        'delay_samples advanced (B)': pair.delay_samples,
        'polarity (B)': pair.polarity,
        'alignment': 'measured (onset + cross-correlation)',
        'output_subtype': subtype,
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
            'polarity': pair.polarity,
            'correlation_confidence': pair.correlation_confidence,
            'phase_diff_weighted_rms_deg': pair.phase_diff_weighted_rms_deg,
            'valid_fraction': pair.valid_fraction,
        },
        'blend': None if blend is None else {
            'ratios': list(blend.ratios),
            'alignment': blend.alignment,
            'worst_cancellation_db': blend.worst_cancellation_db,
            'worst_cancellation_freq_hz': blend.worst_cancellation_freq,
            'notch_freqs_hz': list(blend.notch_freqs),
            'rms_deviation_db': blend.rms_deviation_db,
            'phase_compat_score': blend.phase_compat_score,
            'sensitivity_pm1_sample': blend.sensitivity,
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

