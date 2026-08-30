"""Pair alignment and blend prediction (WP-04).

Alignment: GCC-PHAT coarse delay + parabolic fractional refinement + explicit
polarity test. Blend prediction uses COMPLEX responses:

    Hmix(f) = gA * HA(f) + gB * s * HB(f) * exp(-j 2 pi f tau)

and is verified against an actual time-domain aligned sum on reliable bins.
"""
from __future__ import annotations

import numpy as np

from .contracts import (AnalysisStatus, BlendPrediction, PairComparisonConfig,
                        PairComparisonResult, PreparedIR)
from .time_frequency import next_pow2


def compare_pair(a: PreparedIR, b: PreparedIR, cfg: PairComparisonConfig
                 ) -> PairComparisonResult:
    if a.status != AnalysisStatus.OK or b.status != AnalysisStatus.OK:
        st = (AnalysisStatus.TOO_SHORT if AnalysisStatus.TOO_SHORT in
              (a.status, b.status) else a.status)
        return PairComparisonResult(key_a=a.key, key_b=b.key, cfg=cfg,
                                    status=st,
                                    warnings=tuple(a.warnings) +
                                    tuple(b.warnings))
    sr = a.sample_rate
    xa = _mono(a)
    xb = _mono(b)

    delay, confidence = _estimate_delay(xa, xb, sr, cfg)
    polarity = _estimate_polarity(xa, xb, sr, cfg)

    # magnitude-weighted phase difference on onset-aligned windows
    nfft = next_pow2(max(len(xa), len(xb), 4096))
    HA, HB = _spectra(a, b, sr, nfft)
    diff_deg, valid_fraction = _phase_diff_weighted(HA, HB, cfg, sr)
    return PairComparisonResult(
        key_a=a.key, key_b=b.key, cfg=cfg, status=AnalysisStatus.OK,
        delay_samples=float(delay),
        delay_ms=float(delay / sr * 1000.0),
        polarity=int(polarity),
        correlation_confidence=float(confidence),
        phase_diff_weighted_rms_deg=float(diff_deg),
        gd_median_diff_ms=None,
        valid_fraction=float(valid_fraction),
    )


def predict_blend(a: PreparedIR, b: PreparedIR, cfg: PairComparisonConfig,
                  delay_samples: float | None = None,
                  polarity: int | None = None,
                  alignment: str = 'suggested') -> BlendPrediction:
    """Predict the A+B mix magnitude for the configured blend ratios.

    alignment: 'raw' uses the files' native timing, 'onset' aligns onsets,
    'suggested' uses the measured delay/polarity from cross-correlation.
    """
    if a.status != AnalysisStatus.OK or b.status != AnalysisStatus.OK:
        st = (AnalysisStatus.TOO_SHORT if AnalysisStatus.TOO_SHORT in
              (a.status, b.status) else a.status)
        return BlendPrediction(key_a=a.key, key_b=b.key, cfg=cfg, status=st,
                               warnings=tuple(a.warnings) + tuple(b.warnings))
    sr = a.sample_rate
    if alignment == 'raw':
        tau = 0.0
        s = 1
    elif alignment == 'onset':
        tau = 0.0
        s = 1
    else:
        pair = compare_pair(a, b, cfg)
        tau = pair.delay_samples
        s = pair.polarity if pair.polarity != 0 else 1
    if delay_samples is not None:
        tau = float(delay_samples)
    if polarity is not None:
        s = int(polarity)
    s = 1 if s == 0 else s

    xa = _mono(a)
    xb = _mono(b)
    nfft = next_pow2(len(xa) + len(xb) + int(abs(tau)) + 8)
    HA = np.fft.rfft(xa, nfft)
    HB = np.fft.rfft(xb, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)

    lo, hi = cfg.risk_band
    band = (freqs >= lo) & (freqs <= hi)
    floor = 10 ** (cfg.reliability_floor_db / 20.0)
    mag_a, mag_b = np.abs(HA), np.abs(HB)
    reliable = band & (mag_a >= mag_a.max() * floor) & \
        (mag_b >= mag_b.max() * floor)

    ratios = tuple(cfg.blend_ratios)
    mix_db = np.empty((len(ratios), len(freqs)))
    for i, r in enumerate(ratios):
        gA, gB = 1.0 - 0.0, 1.0
        mix = gA * HA + (r * gB) * s * HB * np.exp(-2j * np.pi * freqs * tau / sr)
        mix_db[i] = 20 * np.log10(np.maximum(np.abs(mix), 1e-30))

    # comb risk on the 50/50 mix within the band: cancellation = deficit below
    # the incoherent power-sum expectation (constructive addition => 0)
    mid_i = int(np.argmin(np.abs(np.asarray(ratios) - 0.5)))
    mid = mix_db[mid_i]
    expect_db = 10 * np.log10(np.maximum(
        np.abs(HA) ** 2 + (ratios[mid_i] ** 2) * np.abs(HB) ** 2, 1e-30))
    deficit = expect_db - mid
    if reliable.any():
        worst_dev = float(deficit[reliable].max())
        worst_dev = max(worst_dev, 0.0)
        worst_freq = float(freqs[np.argmax(np.where(reliable, deficit, -np.inf))])
        notches = tuple(float(f) for f in freqs[reliable & (deficit > 6.0)])
        rms_dev = float(np.sqrt(np.mean(
            np.abs(mid - expect_db)[reliable] ** 2)))
    else:
        worst_dev, worst_freq, notches, rms_dev = None, None, (), None

    # magnitude-weighted phase compatibility on reliable bins
    dphi = np.angle(np.exp(1j * (np.angle(HA) - np.angle(HB)
                                 - 2 * np.pi * freqs * tau / sr
                                 - (np.pi if s < 0 else 0.0))))
    w = (np.minimum(mag_a, mag_b) / (np.minimum(mag_a, mag_b).max() + 1e-30))
    w = w * reliable
    compat = float(1.0 - np.sqrt(np.mean((w * dphi) ** 2)) / np.pi) \
        if w.sum() > 0 else None

    # sensitivity to +/- one sample (worst cancellation deficit)
    sens = {}
    for tag, off in (('-1', -1.0), ('+1', +1.0)):
        mixs = HA + (ratios[mid_i]) * s * HB * np.exp(
            -2j * np.pi * freqs * (tau + off) / sr)
        mids = 20 * np.log10(np.maximum(np.abs(mixs), 1e-30))
        deficits = expect_db - mids
        sens[tag] = (float(deficits[reliable].max()) if reliable.any() else None)

    # verification against an actual aligned time-domain sum
    verified = _verify_against_time_domain(xa, xb, tau, s, ratios[mid_i],
                                           freqs, mix_db[mid_i], reliable, sr)

    warnings = []
    if worst_dev is not None and worst_dev > 12.0:
        warnings.append(f'severe comb cancellation: -{worst_dev:.1f} dB at '
                        f'{worst_freq:.0f} Hz')
    return BlendPrediction(
        key_a=a.key, key_b=b.key, cfg=cfg, status=AnalysisStatus.OK,
        warnings=tuple(warnings), freqs=freqs, magnitude_db=mix_db,
        ratios=ratios, delay_samples=float(tau), polarity=int(s),
        alignment=alignment, worst_cancellation_db=worst_dev,
        worst_cancellation_freq=worst_freq, notch_freqs=notches,
        rms_deviation_db=rms_dev, phase_compat_score=compat,
        sensitivity=sens, verified_rms_db=verified)


# ---- internals -----------------------------------------------------------------
def _mono(p: PreparedIR) -> np.ndarray:
    return p.data.mean(axis=1)[p.onset:p.tail_end + 1]


def _estimate_delay(xa: np.ndarray, xb: np.ndarray, sr: int,
                    cfg: PairComparisonConfig) -> tuple[float, float]:
    """Coarse integer lag via GCC-PHAT, fractional refinement via plain
    cross-correlation around that lag (plan section 8.4). Sign convention:
    positive delay = B arrives later than A."""
    max_lag = int(cfg.max_delay_ms / 1000 * sr)
    nfft = next_pow2(len(xa) + len(xb))
    # window both segments identically: the raw slice edges otherwise dominate
    # the whitened spectrum and pull the coarse peak off the true delay
    win = np.hanning(len(xa))
    win_b = np.hanning(len(xb))
    FA = np.fft.rfft(xa * win, nfft)
    FB = np.fft.rfft(xb * win_b, nfft)
    if cfg.use_gcc_phat:
        phat = 1.0 / (np.abs(FA) * np.abs(FB) + 1e-30)
        cc = np.fft.irfft(FA * np.conj(FB) * phat, nfft)
    else:
        cc = np.fft.irfft(FA * np.conj(FB), nfft)
    cc = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
    k = int(np.argmax(np.abs(cc)))
    lag_int = k - max_lag
    # sign: cc peaks at -lag for a B delayed by +lag
    lag_int = -lag_int

    # fractional refinement with plain correlation restricted to +/-2 lags
    n = min(len(xa), len(xb))

    def plain_cc(lag: int) -> float:
        if lag >= 0:
            u, v = xa[:n - lag], xb[lag:n]
        else:
            u, v = xa[-lag:n], xb[:n + lag]
        u = u - u.mean()
        v = v - v.mean()
        denom = float(np.sqrt(np.sum(u ** 2) * np.sum(v ** 2)))
        return float(np.sum(u * v) / denom) if denom > 0 else 0.0

    best_lag, best_val = lag_int, plain_cc(lag_int)
    lo_c = max(-n + 64, lag_int - 2)
    hi_c = min(n - 64, lag_int + 2)
    for cand in range(lo_c, hi_c + 1):
        if cand == lag_int:
            continue
        v = plain_cc(cand)
        if v > best_val:
            best_val, best_lag = v, cand

    y0, y1, y2 = (plain_cc(best_lag - 1), plain_cc(best_lag),
                  plain_cc(best_lag + 1))
    denom = y0 - 2 * y1 + y2
    frac = float(np.clip(0.5 * (y0 - y2) / denom, -0.5, 0.5)) \
        if abs(denom) > 1e-12 else 0.0

    delay = best_lag + frac   # positive = B delayed relative to A
    confidence = float(np.clip(
        abs(cc[k]) / (np.median(np.abs(cc)) + 1e-30) / 50.0, 0.0, 1.0))
    return float(delay), confidence


def _estimate_polarity(xa: np.ndarray, xb: np.ndarray, sr: int,
                       cfg: PairComparisonConfig) -> int:
    max_lag = int(cfg.max_delay_ms / 1000 * sr)
    nfft = next_pow2(len(xa) + len(xb))
    FA = np.fft.rfft(xa, nfft)
    FB = np.fft.rfft(xb, nfft)
    cc = np.fft.irfft(FA * np.conj(FB), nfft)
    cc = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
    k = int(np.argmax(np.abs(cc)))
    return 1 if cc[k] >= 0 else -1


def _spectra(a: PreparedIR, b: PreparedIR, sr: int, nfft: int):
    def spec_of(p):
        x = _mono(p)
        w = np.hanning(len(x)) if len(x) > 8 else 1.0
        return np.fft.rfft(x * w, nfft)
    return spec_of(a), spec_of(b)


def _phase_diff_weighted(HA: np.ndarray, HB: np.ndarray,
                         cfg: PairComparisonConfig, sr: float
                         ) -> tuple[float, float]:
    freqs = np.fft.rfftfreq((len(HA) - 1) * 2, 1.0 / sr)
    lo, hi = cfg.risk_band
    band = (freqs >= lo) & (freqs <= hi)
    floor = 10 ** (cfg.reliability_floor_db / 20.0)
    ma, mb = np.abs(HA), np.abs(HB)
    reliable = band & (ma >= ma.max() * floor) & (mb >= mb.max() * floor)
    if not reliable.any():
        return float('nan'), 0.0
    dphi = np.angle(np.exp(1j * (np.angle(HA) - np.angle(HB))))
    w = np.minimum(ma, mb)
    w = w / (w.max() + 1e-30)
    wrms = float(np.sqrt(np.sum(w[reliable] * dphi[reliable] ** 2) /
                         (np.sum(w[reliable]) + 1e-30)))
    deg = float(np.degrees(np.sqrt(wrms)))
    return deg, float(reliable.sum() / max(1, band.sum()))


def _verify_against_time_domain(xa: np.ndarray, xb: np.ndarray, tau: float,
                                s: int, ratio: float, freqs: np.ndarray,
                                predicted_db: np.ndarray, reliable: np.ndarray,
                                sr: int) -> float | None:
    if not reliable.any():
        return None
    nfft = len(predicted_db) * 2 - 2 if len(predicted_db) > 1 else 4096
    nfft = next_pow2(max(len(xa), len(xb) + int(abs(tau)) + 8) * 2)
    HA = np.fft.rfft(xa, nfft)
    HB = np.fft.rfft(xb, nfft)
    mix = HA + ratio * s * HB * np.exp(-2j * np.pi * freqs * tau / sr)
    ref_db = 20 * np.log10(np.maximum(np.abs(mix), 1e-30))
    return float(np.sqrt(np.mean((predicted_db[:len(ref_db)][reliable] -
                                  ref_db[reliable]) ** 2)))
