"""Processed-copy export: aligned B, blend WAV, provenance report (WP-08).

All writes are collision-safe (unique suffix) and atomic (temp file +
os.replace). Source files are never modified.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .contracts import (AnalysisStatus, BlendPrediction, FeatureValue,
                        IRProcessingConfig, PairComparisonResult, PreparedIR,
                        ProcessingReport, ResponseFingerprint)
from .pair_preparation import prepare_pair
from .processing import _normalize_peak, apply_alignment, blend_sum, fractional_shift


def unique_dest(dest_dir: str, name: str) -> Path:
    """Atomically reserve and return a unique destination path.

    The zero-byte reservation is deliberately replaced by the atomic writer.
    Callers must either write it or remove it on failure.
    """
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    directory = Path(dest_dir)
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(1, 1000):
        candidate = directory / (name if i == 1 else f'{stem} ({i}){suffix}')
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        else:
            os.close(fd)
            return candidate
    raise RuntimeError(f'no free filename for {name}')


def _atomic_write_wav(path: Path, data: np.ndarray, sr: int, subtype: str) -> None:
    tmp: Path | None = None
    try:
        _validate_wav_payload(data, sr)
        fd, tmp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        if data.shape[1] == 1:
            sf.write(str(tmp), data[:, 0], sr, subtype=subtype, format='WAV')
        else:
            sf.write(str(tmp), data, sr, subtype=subtype, format='WAV')
        os.replace(tmp, path)
    except Exception:
        if tmp is not None:
            _remove_if_exists(tmp)
        _remove_if_exists(path)  # only the reservation created by unique_dest
        raise


def _remove_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _validate_wav_payload(data: np.ndarray, sr: int) -> None:
    if data.ndim != 2 or data.shape[0] == 0 or data.shape[1] == 0:
        raise ValueError('export audio must be a non-empty (frames, channels) array')
    if not np.isfinite(data).all():
        raise ValueError('export audio contains non-finite samples')
    if not isinstance(sr, (int, np.integer)) or sr <= 0:
        raise ValueError('export sample rate must be a positive integer')
    peak = float(np.max(np.abs(data)))
    if peak > 1.0 + 1e-12:
        raise ValueError('export audio exceeds 0 dBFS; set normalize_peak_dbfs to apply headroom')


def _validate_processing_config(cfg: IRProcessingConfig) -> None:
    if cfg.polarity not in (-1, 1):
        raise ValueError('processing polarity must be +1 or -1')
    if not np.isfinite(float(cfg.delay_samples)):
        raise ValueError('processing delay_samples must be finite')
    if cfg.normalize_peak_dbfs is not None:
        target = float(cfg.normalize_peak_dbfs)
        if not np.isfinite(target) or target > 0.0:
            raise ValueError('normalize_peak_dbfs must be finite and at or below 0 dBFS')


def _validate_pair(a: PreparedIR, b: PreparedIR, pair: PairComparisonResult) -> None:
    if pair.status != AnalysisStatus.OK:
        raise ValueError(pair.reason or 'pair analysis must be OK before export')
    if pair.key_a.signature() != a.key.signature() or pair.key_b.signature() != b.key.signature():
        raise ValueError('pair source keys do not match the requested export inputs')
    if pair.polarity not in (-1, 1):
        raise ValueError('pair polarity must be +1 or -1 before export')
    if not np.isfinite(float(pair.delay_samples)):
        raise ValueError('pair delay_samples must be finite before export')


def _source_name(prepared: PreparedIR, suffix: str) -> str:
    name = Path(prepared.key.path).stem
    return f'{name} {suffix}.wav'


def export_processed(prepared: PreparedIR, cfg: IRProcessingConfig,
                     dest_dir: str, suffix: str = 'aligned') -> ProcessingReport:
    """Write an aligned/polarity-corrected copy of the prepared IR."""
    _validate_processing_config(cfg)
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
    _validate_pair(a, b, pair)
    if cfg is not None:
        _validate_processing_config(cfg)
    prepared = prepare_pair(a, b)
    if prepared.status != AnalysisStatus.OK:
        raise ValueError(prepared.reason or
                         'both IRs must analyze cleanly before aligned-B export')
    subtype = cfg.output_subtype if cfg else 'PCM_24'
    advance = float(pair.delay_samples)
    s = pair.polarity
    data_b = np.array(prepared.data_b, dtype=np.float64, copy=True)
    if s == -1:
        data_b = -data_b
    data_b = fractional_shift(data_b, advance,
                              output_frames=len(data_b) + int(np.ceil(abs(advance))))
    warnings = list(prepared.warnings)
    data_b = _normalize_peak(data_b, cfg.normalize_peak_dbfs if cfg else None, warnings)

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
    _validate_pair(a, b, pair)
    if cfg is not None:
        _validate_processing_config(cfg)
    if not np.isfinite(float(ratio_b)) or not 0.0 <= float(ratio_b) <= 1.0:
        raise ValueError('blend ratio_b must be finite and between 0 and 1')
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
    if cfg is not None and cfg.normalize_peak_dbfs is not None:
        applied['normalize_peak_dbfs'] = cfg.normalize_peak_dbfs
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
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f'.{dest.name}.', suffix='.tmp', dir=dest.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.write_text(json.dumps(doc, indent=2), encoding='utf-8')
        os.replace(tmp, dest)
    except Exception:
        if tmp is not None:
            _remove_if_exists(tmp)
        _remove_if_exists(dest)
        raise
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

