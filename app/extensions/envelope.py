"""Impulse envelope and transient metrics (WP-02).

All timing is measured on onset-relative time. Gain-independent metrics use the
normalized envelope; absolute peak/RMS stay in PreparedIR metadata.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import hilbert

from .channel_policy import power_aggregate, rms_aggregate
from .contracts import (AnalysisStatus, EnvelopeConfig, EnvelopeResult,
                        PreparedIR)


def compute_envelope(prepared: PreparedIR, cfg: EnvelopeConfig) -> EnvelopeResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return EnvelopeResult(key=prepared.key, cfg=cfg, status=prepared.status,
                              warnings=prepared.warnings)
    sr = prepared.sample_rate
    x = prepared.data
    onset = prepared.onset
    seg = x[onset:]                                 # (n, ch)
    n_ch = seg.shape[1]

    # Stereo channel policy: magnitude/energy reductions use power aggregation
    # (mean of per-channel squares), never a signed channel mean, so an
    # anti-phase pair [x, -x] keeps its energy. For mono each aggregate below
    # reduces to exactly the legacy single-channel signal.
    p2 = power_aggregate(seg, axis=1)               # energy signal (x**2 mono)
    # analytic envelope is per-channel along TIME (axis=0); hilbert() would
    # otherwise transform the length-1 channel axis and degenerate mono to |x|
    env_ch = np.abs(hilbert(seg, axis=0))           # per-channel analytic env
    hilb = rms_aggregate(env_ch, axis=1)            # |hilbert(x)| for mono
    time_ms = np.arange(len(seg), dtype=np.float64) / sr * 1000.0

    # short-window RMS envelope (stable energy comparisons)
    win = max(1, int(cfg.rms_window_ms * sr / 1000))
    sq = p2
    cs = np.concatenate(([0.0], np.cumsum(sq)))
    idx0 = np.arange(0, len(sq))
    w_end = np.minimum(idx0 + win, len(sq))
    w_start = np.maximum(idx0 - win, 0)
    rms_env = np.sqrt((cs[w_end] - cs[w_start]) /
                      np.maximum(w_end - w_start, 1))

    def _norm(a: np.ndarray) -> np.ndarray:
        m = float(a.max())
        return a / m if m > 0 else a

    hilbert_env = _norm(hilb)
    rms_env_n = _norm(rms_env)
    mono_seg = np.max(np.abs(seg), axis=1)
    peak_hold = np.maximum.accumulate(_norm(mono_seg)) if cfg.peak_hold else None

    # peak time / polarity on the dominant channel's signed signal (mono: the
    # only channel, identical to the legacy channel-mean behavior)
    if n_ch == 1:
        ref = seg[:, 0]
    else:
        ref = seg[:, int(np.argmax(np.max(np.abs(seg), axis=0)))]
    peak_rel = int(np.argmax(np.abs(ref)))
    polarity = 1 if ref[peak_rel] >= 0 else -1
    peak_time_ms = peak_rel / sr * 1000.0

    # rise time 10-90% (validity-guarded)
    rise_ms, rise_valid, rise_reason = _rise_time(
        hilbert_env, peak_rel, sr, cfg)

    # energy fractions on the power-aggregated energy signal
    energy = np.cumsum(p2.astype(np.float64))
    total = energy[-1] if len(energy) else 0.0

    def _frac(ms: float) -> float | None:
        if total <= 0:
            return None
        i = min(int(ms / 1000.0 * sr), len(energy) - 1)
        return float(energy[i] / total)

    e1, e5 = _frac(cfg.early_windows_ms[0]), _frac(cfg.early_windows_ms[1])
    if total > 0:
        i_late = min(int(cfg.late_from_ms / 1000.0 * sr), len(energy) - 1)
        early = energy[i_late]
        late = total - early
        elr = float(early / late) if late > 1e-30 else None
    else:
        elr = None

    centroid = (float(np.sum(time_ms * p2) / np.sum(p2))
                if np.sum(p2) > 0 else None)

    peak_abs = float(np.max(np.sqrt(p2))) if len(p2) else 0.0
    rms_abs = (float(np.sqrt(np.mean(p2)))
               if len(p2) else 0.0)
    crest = peak_abs / rms_abs if rms_abs > 0 else None

    tail_ms = (prepared.tail_end - onset) / sr * 1000.0

    warnings = list(prepared.warnings)
    return EnvelopeResult(
        key=prepared.key, cfg=cfg, status=AnalysisStatus.OK,
        warnings=tuple(warnings), time_ms=time_ms, hilbert_env=hilbert_env,
        rms_env=rms_env_n, peak_hold_env=peak_hold, peak_time_ms=peak_time_ms,
        peak_polarity=polarity, rise_time_ms=rise_ms, rise_valid=rise_valid,
        rise_reason=rise_reason, early_energy_1ms=e1, early_energy_5ms=e5,
        early_late_ratio=elr, centroid_ms=centroid, crest_factor=crest,
        tail_end_ms=tail_ms,
    )


def _rise_time(env: np.ndarray, peak_rel: int, sr: int, cfg: EnvelopeConfig):
    """10-90% rise time of the normalized envelope, with validity rules."""
    if peak_rel <= 1 or peak_rel >= len(env):
        return None, False, 'impulse too short for a rise-time measurement'
    pre = env[:peak_rel]
    below = pre[pre < cfg.rise_from * env[peak_rel]]
    if len(below) == len(pre):
        return None, False, 'envelope never reaches 10% before peak'
    i10 = int(np.argmax(pre >= cfg.rise_from * env[peak_rel]))
    i90 = int(np.argmax(pre >= cfg.rise_to * env[peak_rel]))
    if i90 <= i10:
        return None, False, '10% and 90% points coincide (one-sample peak)'
    rise = (i90 - i10) / sr * 1000.0
    if rise < 0.02:
        return None, False, 'rise shorter than measurement resolution'
    return rise, True, ''
