"""Onset-compensated phase, group delay, minimum/excess phase (WP-04).

Phase conventions:
- Time zero is the detected onset. The FFT is taken on the canonical useful
  window (onset..tail) so a minimum-phase IR has near-linear wrapped phase.
- Unwrapping and group delay are only computed where the magnitude passes the
  reliability threshold; invalid bins are NaN, never interpolated silently.
- Stereo channels are transformed separately (never power-averaged for phase).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import hilbert

from .contracts import (AnalysisStatus, PhaseConfig, PhaseResult, PreparedIR)
from .time_frequency import next_pow2


def compute_phase(prepared: PreparedIR, cfg: PhaseConfig) -> PhaseResult:
    if prepared.status != AnalysisStatus.OK or prepared.data is None:
        return PhaseResult(key=prepared.key, cfg=cfg, status=prepared.status,
                           warnings=prepared.warnings)
    sr = prepared.sample_rate
    usable = prepared.data[prepared.onset:prepared.tail_end + 1]
    if len(usable) < 64:
        return PhaseResult(key=prepared.key, cfg=cfg,
                           status=AnalysisStatus.TOO_SHORT,
                           warnings=('useful segment too short for phase',))

    nfft = next_pow2(len(usable) * 2)
    n_ch = usable.shape[1]
    window = np.hanning(len(usable))[:, None]

    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    in_band = (freqs >= cfg.fmin) & (freqs <= cfg.fmax)
    spec = np.fft.rfft(usable * window, nfft, axis=0)     # (n_bins, n_ch)
    mag = np.abs(spec)
    peak_mag = float(mag.max())
    if peak_mag > 0:
        valid_bins = mag >= peak_mag * 10 ** (cfg.rel_threshold_db / 20.0)
    else:
        valid_bins = np.zeros_like(mag, dtype=bool)
    # B11: validity is decided PER CHANNEL — a silent channel never inherits
    # validity from an active neighbour, so its phase/GD bins stay NaN.
    valid = valid_bins & in_band[:, None]                 # (n_bins, n_ch)
    valid[0, :] = False                                   # DC invalid

    phase = np.full((len(freqs), n_ch), np.nan)
    group_delay_ms = np.full((len(freqs), n_ch), np.nan)
    for ch in range(n_ch):
        valid_ch = valid[:, ch]
        wrapped = np.angle(spec[:, ch])
        unwrapped = _masked_unwrap(wrapped, valid_ch)
        # onset compensation: remove the linear phase of the onset offset.
        # FFT of the onset-aligned window is already onset-referenced at t=0
        # (first usable sample), so no extra linear term is removed here.
        phase[:, ch] = np.where(valid_ch, unwrapped, np.nan)
        if int(valid_ch.sum()) >= 3:
            f = freqs[valid_ch]
            dphi = np.gradient(phase[valid_ch, ch])
            # df between adjacent kept bins
            gd_s = -dphi / (2 * np.pi * np.gradient(f))
            group_delay_ms[valid_ch, ch] = gd_s * 1000.0

    min_phase_rad = None
    excess_phase_rad = None
    if cfg.min_phase and int(valid.sum()) >= 3:
        try:
            min_phase_rad, excess_phase_rad = _minimum_excess_phase(
                mag, valid, nfft, phase)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError):
            min_phase_rad = excess_phase_rad = None

    n_in_band = max(1, int(in_band.sum()))
    coverage = float(valid.sum(axis=0).mean() / n_in_band)
    warnings = []
    if coverage < 0.5:
        warnings.append(f'low valid-phase coverage: {coverage:.0%} in band')
    return PhaseResult(key=prepared.key, cfg=cfg, status=AnalysisStatus.OK,
                       warnings=tuple(warnings), freqs=freqs, phase_rad=phase,
                       group_delay_ms=group_delay_ms, valid_mask=valid,
                       min_phase_rad=min_phase_rad,
                       excess_phase_rad=excess_phase_rad, coverage=coverage)


def _masked_unwrap(wrapped: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Unwrap only across consecutive valid bins; invalid runs stay separate."""
    out = np.full_like(wrapped, np.nan)
    idx = np.nonzero(valid)[0]
    if len(idx) == 0:
        return out
    run_start = idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a == 1:
            pass
        else:
            # close the current run
            out[run_start:a + 1] = np.unwrap(wrapped[run_start:a + 1])
            run_start = b
    out[run_start:idx[-1] + 1] = np.unwrap(wrapped[run_start:idx[-1] + 1])
    return out


def _minimum_excess_phase(mag: np.ndarray, valid: np.ndarray, nfft: int,
                          phase_total: np.ndarray):
    """Minimum-phase spectrum from the log magnitude (cepstral method).

    theta_min(f) = Im{ FFT(cepstrum with doubled causal part) } — exact for a
    time origin at the impulse start. Excess = wrapped(total - minimum).
    Invalid bins are zeroed in the input, which smooths their influence; the
    valid mask on the output marks where the decomposition is trustworthy.
    """
    n_ch = mag.shape[1]
    log_mag = np.log(np.maximum(mag, 1e-30))
    out_min = np.full_like(log_mag, np.nan)
    out_exc = np.full_like(log_mag, np.nan)
    for ch in range(n_ch):
        valid_ch = valid[:, ch]
        lm = np.where(valid_ch, log_mag[:, ch], 0.0)
        full = np.concatenate([lm, lm[-2:0:-1]])
        c = np.fft.ifft(full).real
        c_min = np.zeros_like(c)
        c_min[0] = c[0]
        half = len(c) // 2
        c_min[1:half] = 2.0 * c[1:half]
        if len(c) % 2 == 0:
            c_min[half] = c[half]
        theta_min = np.imag(np.fft.fft(c_min))[:len(lm)]
        out_min[:, ch] = np.where(valid_ch, theta_min, np.nan)
        out_exc[:, ch] = np.where(
            valid_ch, np.angle(np.exp(1j * (phase_total[:, ch] - theta_min))),
            np.nan)
    return out_min, out_exc


def impulse_min_phase_check(x: np.ndarray) -> float:
    """Helper: energy-before-onset ratio after minimum-phase conversion (0..1)."""
    env = np.abs(hilbert(x))
    return float(env[0] / (env.max() + 1e-30))
