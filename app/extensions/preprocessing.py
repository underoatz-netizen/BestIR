"""Canonical signal preparation (WP-02).

Every analysis starts here so all views agree about onset, time origin, tail
bounds, noise floor, and channel handling. See plan section 7.
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, AudioBuffer, PreprocessingConfig,
                        PreparedIR)


def _peak_window_rms(x: np.ndarray, center: int, half: int) -> float:
    a = max(0, center - half)
    b = min(len(x), center + half)
    seg = x[a:b]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def prepare(buffer: AudioBuffer, cfg: PreprocessingConfig) -> PreparedIR:
    sr = buffer.sample_rate
    x = np.array(buffer.data, dtype=np.float64, copy=True)  # we may mutate the copy

    if x.size == 0 or len(x) < max(16, int(cfg.min_length_ms * sr / 1000)):
        return _status_result(buffer, cfg, AnalysisStatus.TOO_SHORT,
                              warning='file shorter than minimum analysis length')
    if not np.all(np.isfinite(x)):
        return _status_result(buffer, cfg, AnalysisStatus.NONFINITE,
                              warning='non-finite samples present')

    warnings = []

    # ---- first-pass onset on the raw copy (peak position is DC-insensitive) ----
    raw_peak_env = np.max(np.abs(x), axis=1)
    raw_peak = float(raw_peak_env.max())
    if raw_peak <= 1e-12:
        return _status_result(buffer, cfg, AnalysisStatus.SILENT,
                              warning='peak below -240 dBFS')
    above0 = np.nonzero(raw_peak_env > raw_peak * cfg.onset_rel_threshold)[0]
    raw_onset = int(above0[0]) if len(above0) else 0

    # ---- DC removal: use the PRE-ONSET mean only. The global mean of a
    # one-sided impulse is signal energy, not DC; removing it would inject a
    # persistent step into the tail. Without a pre-onset region we skip.
    n_pre = min(raw_onset, max(8, int(cfg.noise_window_ms * sr / 1000)))
    if cfg.dc_remove and raw_onset >= 8:
        x = x - x[raw_onset - n_pre:raw_onset].mean(axis=0, keepdims=True)
    elif cfg.dc_remove:
        warnings.append('no pre-onset region: DC removal skipped')

    peak = float(np.max(np.abs(x)))
    if peak <= 1e-12:
        return _status_result(buffer, cfg, AnalysisStatus.SILENT,
                              warning='peak below -240 dBFS after DC removal')

    if peak >= 0.999:
        warnings.append('input near or at full scale (possible clipping)')

    mono_peak_env = np.max(np.abs(x), axis=1)
    peak_index = int(np.argmax(mono_peak_env))

    # ---- onset: first crossing of peak * threshold with local-energy confirm ----
    thr = peak * cfg.onset_rel_threshold
    above = np.nonzero(mono_peak_env > thr)[0]
    onset = int(above[0]) if len(above) else 0
    # confirm with local energy (guards against an isolated single-sample blip)
    half = max(1, int(0.002 * sr))
    if _peak_window_rms(mono_peak_env, onset, half) < peak * cfg.onset_rel_threshold * 0.5:
        later = np.nonzero(mono_peak_env[onset:] > thr)[0]
        onset = int(onset + later[0]) if len(later) else onset
    # keep a little pre-onset audio for display/pre-arrival checks
    onset = int(max(0, onset - int(cfg.onset_backtrack_ms * sr / 1000)))
    onset_conf = _onset_confidence(mono_peak_env, onset, peak, sr, cfg)

    # ---- noise floor: RMS in the pre-onset window ----------------------------
    n_pre2 = min(onset, max(8, int(cfg.noise_window_ms * sr / 1000)))
    pre = x[max(0, onset - n_pre2):onset] if onset > 0 else x[:0]
    noise_rms = (float(np.sqrt(np.mean(pre ** 2)))
                 if pre.size else 0.0)

    # ---- useful tail: last window above peak-RMS * 10^(dB/20) -----------------
    rms_win = max(1, int(0.005 * sr))
    mono_sq = (x ** 2).mean(axis=1)
    cs = np.concatenate(([0.0], np.cumsum(mono_sq)))
    w0 = np.arange(0, len(mono_sq), rms_win)
    w1 = np.minimum(w0 + rms_win, len(mono_sq))
    env_rms = np.sqrt((cs[w1] - cs[w0]) / np.maximum(w1 - w0, 1))
    peak_rms = float(env_rms.max()) if len(env_rms) else peak
    tail_thr = peak_rms * 10 ** (cfg.tail_rel_threshold_db / 20.0)
    above_t = np.nonzero(env_rms > tail_thr)[0]
    if len(above_t):
        tail_end = int(min(w1[above_t[-1]], len(x) - 1))
    else:
        tail_end = len(x) - 1
    tail_end = max(tail_end, onset)

    # ---- analysis cap ---------------------------------------------------------
    max_frames = int(cfg.max_length_ms * sr / 1000)
    keep_end = min(len(x), max(onset + max_frames, tail_end + rms_win))
    x = x[:keep_end]
    tail_end = min(tail_end, len(x) - 1)

    x.setflags(write=False)
    rms = float(np.sqrt(np.mean(x ** 2)))
    return PreparedIR(
        key=buffer.key, cfg=cfg, status=AnalysisStatus.OK,
        warnings=tuple(warnings), data=x, sample_rate=sr,
        onset=onset, onset_confidence=onset_conf, peak_index=peak_index,
        tail_end=tail_end, noise_floor_rms=noise_rms, peak_value=peak,
        rms_value=rms,
    )


def _onset_confidence(peak_env: np.ndarray, onset: int, peak: float,
                      sr: int, cfg: PreprocessingConfig) -> float:
    """1.0 when pre-onset audio is far below the onset step, 0.0 when buried."""
    n_pre = min(onset, max(8, int(cfg.noise_window_ms * sr / 1000)))
    pre = peak_env[max(0, onset - n_pre):onset]
    pre_peak = float(pre.max()) if pre.size else 0.0
    if peak <= 0:
        return 0.0
    ratio = pre_peak / peak
    return float(np.clip(1.0 - ratio * 5.0, 0.0, 1.0))


def _status_result(buffer: AudioBuffer, cfg: PreprocessingConfig,
                   status: AnalysisStatus, warning: str) -> PreparedIR:
    return PreparedIR(key=buffer.key, cfg=cfg, status=status,
                      warnings=(warning,), sample_rate=buffer.sample_rate)
