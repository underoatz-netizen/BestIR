"""Pair alignment and blend prediction (WP-04).

Alignment: GCC-PHAT coarse delay + parabolic fractional refinement + explicit
polarity test. Blend prediction uses COMPLEX responses:

    Hmix(f) = gA * HA(f) + gB * s * HB(f) * exp(+j 2 pi f tau)

and is verified against an actual time-domain aligned sum on reliable bins.
"""
from __future__ import annotations

import numpy as np

from .channel_policy import mono_or_rms
from .contracts import (AnalysisStatus, BlendPrediction, CancellationRisk,
                        PairComparisonConfig, PairComparisonResult, PreparedIR)
from .pair_preparation import PreparedPair, prepare_pair
from .processing import blend_gains, blend_sum
from .time_frequency import next_pow2


def compare_pair(a: PreparedIR, b: PreparedIR, cfg: PairComparisonConfig
                  ) -> PairComparisonResult:
    prepared = prepare_pair(a, b)
    if prepared.status != AnalysisStatus.OK:
        return _invalid_pair_result(a, b, cfg, prepared)
    sr = prepared.sample_rate
    xa = _mono(prepared.data_a)
    xb = _mono(prepared.data_b)

    total_delay, confidence = _estimate_delay(xa, xb, sr, cfg)
    polarity = _estimate_polarity(xa, xb, sr, cfg)
    onset_delay = prepared.onset_delay_samples
    residual_delay = total_delay - onset_delay

    # Full buffers retain each source's independent leading-silence timing.
    nfft = next_pow2(max(len(xa), len(xb), 4096))
    HA, HB = _spectra(xa, xb, nfft)
    diff_deg, valid_fraction = _phase_diff_weighted(HA, HB, cfg, sr)
    return PairComparisonResult(
        key_a=a.key, key_b=b.key, cfg=cfg, status=AnalysisStatus.OK,
        warnings=prepared.warnings,
        delay_samples=float(total_delay),
        delay_ms=float(total_delay / sr * 1000.0),
        polarity=int(polarity),
        correlation_confidence=float(confidence),
        phase_diff_weighted_rms_deg=float(diff_deg),
        gd_median_diff_ms=None,
        valid_fraction=float(valid_fraction),
        onset_delay_samples=float(onset_delay),
        residual_delay_samples=float(residual_delay),
        source_sample_rate_a=prepared.source_sample_rate_a,
        source_sample_rate_b=prepared.source_sample_rate_b,
        analysis_sample_rate=prepared.sample_rate,
    )


def predict_blend(a: PreparedIR, b: PreparedIR, cfg: PairComparisonConfig,
                  delay_samples: float | None = None,
                  polarity: int | None = None,
                  alignment: str = 'suggested') -> BlendPrediction:
    """Predict the A+B mix magnitude for the configured blend ratios.

    alignment: 'raw' uses the files' native timing, 'onset' aligns onsets,
    'suggested' uses the measured delay/polarity from cross-correlation.
    """
    prepared = prepare_pair(a, b)
    if prepared.status != AnalysisStatus.OK:
        return _invalid_blend_prediction(a, b, cfg, prepared, alignment)
    sr = prepared.sample_rate
    onset_component = 0.0
    residual_component = 0.0
    if alignment == 'raw':
        tau = 0.0
        s = 1
    elif alignment == 'onset':
        tau = prepared.onset_delay_samples
        s = 1
        onset_component = tau
    else:
        pair = compare_pair(a, b, cfg)
        if pair.status != AnalysisStatus.OK:
            return BlendPrediction(
                key_a=a.key, key_b=b.key, cfg=cfg, status=pair.status,
                warnings=pair.warnings, alignment=alignment,
                source_sample_rate_a=prepared.source_sample_rate_a,
                source_sample_rate_b=prepared.source_sample_rate_b,
                analysis_sample_rate=prepared.sample_rate,
                reason=pair.reason,
            )
        tau = pair.delay_samples
        s = pair.polarity if pair.polarity != 0 else 1
        onset_component = pair.onset_delay_samples
        residual_component = pair.residual_delay_samples
    if delay_samples is not None:
        tau = float(delay_samples)
        residual_component = tau - onset_component
    if polarity is not None:
        s = int(polarity)
    s = 1 if s == 0 else s

    xa = _mono(prepared.data_a)
    xb = _mono(prepared.data_b)
    nfft = next_pow2(len(xa) + len(xb) + int(np.ceil(abs(tau))) + 8)
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
    risk_by_ratio = {}
    expectation_db = []
    # Positive delay means B arrives later, so prediction advances it.
    phase_ramp = np.exp(2j * np.pi * freqs * tau / sr)
    for i, r in enumerate(ratios):
        ratio = float(r)
        gA, gB = blend_gains(ratio)
        mix = gA * HA + gB * s * HB * phase_ramp
        mix_db[i] = 20 * np.log10(np.maximum(np.abs(mix), 1e-30))
        expect_db = 10 * np.log10(np.maximum(
            np.abs(gA * HA) ** 2 + np.abs(gB * HB) ** 2, 1e-30))
        expectation_db.append(expect_db)
        deficit = expect_db - mix_db[i]
        if reliable.any():
            worst_i = int(np.argmax(np.where(reliable, deficit, -np.inf)))
            worst_dev = max(float(deficit[worst_i]), 0.0)
            worst_freq = float(freqs[worst_i])
            notches = tuple(float(f) for f in freqs[reliable & (deficit > 6.0)])
            sensitivity = {}
            for tag, off in (('-1', -1.0), ('+1', +1.0)):
                offset_mix = gA * HA + gB * s * HB * np.exp(
                    2j * np.pi * freqs * (tau + off) / sr)
                offset_db = 20 * np.log10(np.maximum(np.abs(offset_mix), 1e-30))
                sensitivity[tag] = max(
                    float((expect_db - offset_db)[reliable].max()), 0.0)
        else:
            worst_dev, worst_freq, notches = None, None, ()
            sensitivity = {'-1': None, '+1': None}
        risk_by_ratio[ratio] = CancellationRisk(
            worst_cancellation_db=worst_dev,
            worst_cancellation_freq=worst_freq,
            notch_freqs=notches,
            sensitivity=sensitivity,
        )

    # Compatibility summary: retain the configured ratio nearest 50% B.
    mid_i = int(np.argmin(np.abs(np.asarray(ratios) - 0.5)))
    mid = mix_db[mid_i]
    expect_db = expectation_db[mid_i]
    reference_risk = risk_by_ratio[float(ratios[mid_i])]
    if reliable.any():
        rms_dev = float(np.sqrt(np.mean(
            np.abs(mid - expect_db)[reliable] ** 2)))
    else:
        rms_dev = None

    # magnitude-weighted phase compatibility on reliable bins
    dphi = np.angle(np.exp(1j * (np.angle(HA) - np.angle(HB)
                                 - 2 * np.pi * freqs * tau / sr
                                 - (np.pi if s < 0 else 0.0))))
    w = (np.minimum(mag_a, mag_b) / (np.minimum(mag_a, mag_b).max() + 1e-30))
    w = w * reliable
    compat = float(1.0 - np.sqrt(np.mean((w * dphi) ** 2)) / np.pi) \
        if w.sum() > 0 else None

    # verification against an actual aligned time-domain sum
    verified = _verify_against_time_domain(a, b, cfg, tau, s, ratios[mid_i],
                                            mix_db[mid_i], reliable, nfft)

    warnings = list(prepared.warnings)
    if (reference_risk.worst_cancellation_db is not None and
            reference_risk.worst_cancellation_db > 12.0):
        warnings.append(
            f'severe comb cancellation: '
            f'-{reference_risk.worst_cancellation_db:.1f} dB at '
            f'{reference_risk.worst_cancellation_freq:.0f} Hz')
    return BlendPrediction(
        key_a=a.key, key_b=b.key, cfg=cfg, status=AnalysisStatus.OK,
        warnings=tuple(warnings), freqs=freqs, magnitude_db=mix_db,
        ratios=ratios, delay_samples=float(tau), polarity=int(s),
        alignment=alignment,
        worst_cancellation_db=reference_risk.worst_cancellation_db,
        worst_cancellation_freq=reference_risk.worst_cancellation_freq,
        notch_freqs=reference_risk.notch_freqs,
        rms_deviation_db=rms_dev, phase_compat_score=compat,
        sensitivity=dict(reference_risk.sensitivity), verified_rms_db=verified,
        risk_by_ratio=risk_by_ratio,
        onset_delay_samples=float(onset_component),
        residual_delay_samples=float(residual_component),
        source_sample_rate_a=prepared.source_sample_rate_a,
        source_sample_rate_b=prepared.source_sample_rate_b,
        analysis_sample_rate=prepared.sample_rate)


# ---- internals -----------------------------------------------------------------
def _invalid_pair_result(a: PreparedIR, b: PreparedIR,
                         cfg: PairComparisonConfig,
                         prepared: PreparedPair) -> PairComparisonResult:
    return PairComparisonResult(
        key_a=a.key, key_b=b.key, cfg=cfg, status=prepared.status,
        warnings=prepared.warnings,
        source_sample_rate_a=prepared.source_sample_rate_a,
        source_sample_rate_b=prepared.source_sample_rate_b,
        analysis_sample_rate=prepared.sample_rate,
        reason=prepared.reason,
    )


def _invalid_blend_prediction(a: PreparedIR, b: PreparedIR,
                              cfg: PairComparisonConfig,
                              prepared: PreparedPair,
                              alignment: str) -> BlendPrediction:
    return BlendPrediction(
        key_a=a.key, key_b=b.key, cfg=cfg, status=prepared.status,
        warnings=prepared.warnings, alignment=alignment,
        source_sample_rate_a=prepared.source_sample_rate_a,
        source_sample_rate_b=prepared.source_sample_rate_b,
        analysis_sample_rate=prepared.sample_rate,
        reason=prepared.reason,
    )


def _mono(data: np.ndarray) -> np.ndarray:
    # Channel reduction routed through the central channel policy: mono stays
    # byte-identical, but a multi-channel anti-phase pair [x, -x] becomes |x|
    # (RMS) instead of cancelling to near-silence (which would break GCC-PHAT
    # delay estimation and blend prediction).
    return mono_or_rms(data, axis=1)


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


def _spectra(xa: np.ndarray, xb: np.ndarray, nfft: int):
    def spec_of(x):
        w = np.hanning(len(x)) if len(x) > 8 else 1.0
        return np.fft.rfft(x * w, nfft)
    return spec_of(xa), spec_of(xb)


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
    # single square root: wrms is already the weighted radians RMS (B10)
    deg = float(np.degrees(wrms))
    return deg, float(reliable.sum() / max(1, band.sum()))


def _verify_against_time_domain(a: PreparedIR, b: PreparedIR,
                                cfg: PairComparisonConfig, tau: float, s: int,
                                ratio: float, predicted_db: np.ndarray,
                                reliable: np.ndarray, nfft: int) -> float | None:
    if not reliable.any():
        return None
    pair = PairComparisonResult(
        key_a=a.key, key_b=b.key, cfg=cfg, status=AnalysisStatus.OK,
        delay_samples=float(tau), polarity=int(s),
    )
    mix, _, _ = blend_sum(a, b, pair, ratio)
    # same channel-policy reduction as the prediction path: mono is unchanged,
    # stereo anti-phase channels are RMS-combined instead of cancelling.
    mono_mix = mono_or_rms(mix, axis=1)
    ref_db = 20 * np.log10(np.maximum(np.abs(np.fft.rfft(mono_mix, nfft)), 1e-30))
    return float(np.sqrt(np.mean((predicted_db[reliable] -
                                  ref_db[reliable]) ** 2)))
