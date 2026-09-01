"""WP-08 gates: non-destructive processing, collision-safe export, provenance."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AnalysisStatus, AudioBuffer, IRProcessingConfig,
                                       PairComparisonConfig, PairComparisonResult,
                                       PreprocessingConfig, SourceKey)
from app.extensions.pair_compare import _estimate_delay, compare_pair, predict_blend
from app.extensions.preprocessing import prepare
from app.extensions.processing import apply_alignment, blend_sum, fractional_shift
from app.extensions.processing_export import (export_blend, export_pair_aligned_b,
                                              export_pair_report,
                                              export_processed)
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


def _sine_burst(sample_rate, frequency_hz, tone_duration_s):
    lead_frames = int(round(sample_rate * 0.003))
    tone_frames = int(round(sample_rate * tone_duration_s))
    t = np.arange(tone_frames, dtype=np.float64) / sample_rate
    out = np.zeros(lead_frames + tone_frames, dtype=np.float64)
    out[lead_frames:] = 0.5 * np.sin(2.0 * np.pi * frequency_hz * t)
    return out


def _tone_measurement(data, sample_rate):
    x = np.asarray(data, dtype=np.float64)
    if x.ndim == 2:
        x = x[:, 0]
    peak = float(np.max(np.abs(x)))
    active = np.flatnonzero(np.abs(x) > peak * 1e-3)
    assert len(active) > 8
    tone = x[active[0]:active[-1] + 1]
    freqs = np.fft.rfftfreq(len(tone), 1.0 / sample_rate)
    spectrum = np.abs(np.fft.rfft(tone * np.hanning(len(tone))))
    peak_bin = int(np.argmax(spectrum[1:]) + 1)
    duration_s = (active[-1] - active[0] + 1) / sample_rate
    return float(freqs[peak_bin]), float(duration_s)


def _reasoned_channel_rejection(call):
    try:
        outcome = call()
    except Exception as exc:
        detail = f'{type(exc).__name__}: {exc}'
        text = detail.lower()
        return ('channel' in text or 'mismatch' in text), detail

    status = getattr(outcome, 'status', None)
    if status is not None:
        value = getattr(status, 'value', status)
        return value != AnalysisStatus.OK.value, f'status={value!r}'

    if isinstance(outcome, tuple) and len(outcome) >= 3:
        data, _, warnings = outcome[:3]
        return data is None and bool(warnings), f'data={type(data).__name__}, warnings={warnings!r}'

    reason = getattr(outcome, 'reason', None)
    return bool(reason), f'outcome={type(outcome).__name__}, reason={reason!r}'


@pytest.mark.parametrize(
    ('a_sr', 'b_sr'),
    ((48000, 96000), (96000, 48000)),
    ids=('a48_b96', 'a96_b48'),
)
def test_b02_mixed_rate_b_only_blend_and_export_preserve_physical_tone(
        tmp_path, a_sr, b_sr):
    """B is physically resampled to A's rate, not merely relabeled."""
    frequency_hz = 1000.0
    tone_duration_s = 0.030
    pa = _prep(_sine_burst(a_sr, frequency_hz, tone_duration_s), a_sr)
    pb = _prep(_sine_burst(b_sr, frequency_hz, tone_duration_s), b_sr)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    cfg = PairComparisonConfig(blend_ratios=(1.0,))
    pair = PairComparisonResult(
        key_a=pa.key, key_b=pb.key, cfg=cfg, status=AnalysisStatus.OK,
        delay_samples=0.0, polarity=1,
    )

    prediction = predict_blend(pa, pb, cfg, delay_samples=0.0, polarity=1,
                               alignment='raw')
    mix, output_sr, _ = blend_sum(pa, pb, pair, ratio_b=1.0)
    report = export_blend(pa, pb, pair, ratio_b=1.0, dest_dir=str(tmp_path))
    exported, exported_sr = sf.read(report.output_path, always_2d=True)

    assert prediction.status == AnalysisStatus.OK
    assert output_sr == a_sr
    assert exported_sr == a_sr
    nfft = (len(prediction.freqs) - 1) * 2
    actual_db = 20.0 * np.log10(np.maximum(
        np.abs(np.fft.rfft(mix[:, 0], nfft)), 1e-30))
    reliable = (actual_db > actual_db.max() - 60.0) & \
        (prediction.magnitude_db[0] > prediction.magnitude_db[0].max() - 60.0)
    preview_error = float(np.sqrt(np.mean(
        (prediction.magnitude_db[0, reliable] - actual_db[reliable]) ** 2)))
    assert preview_error < 0.1, preview_error

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    preview_freq = float(prediction.freqs[
        int(np.argmax(prediction.magnitude_db[0, 1:]) + 1)])
    mix_freq, mix_duration_s = _tone_measurement(mix, output_sr)
    export_freq, export_duration_s = _tone_measurement(exported, exported_sr)
    assert (
        abs(preview_freq - frequency_hz) < 80.0 and
        abs(mix_freq - frequency_hz) < 80.0 and
        abs(export_freq - frequency_hz) < 80.0 and
        abs(mix_duration_s - tone_duration_s) < 0.001 and
        abs(export_duration_s - tone_duration_s) < 0.001
    ), (f'expected {frequency_hz} Hz for {tone_duration_s:.3f} s; '
        f'preview={preview_freq:.1f} Hz, mix={mix_freq:.1f} Hz/'
        f'{mix_duration_s:.4f} s, export={export_freq:.1f} Hz/'
        f'{export_duration_s:.4f} s')


def test_b02_unequal_channels_are_reasonedly_rejected(tmp_path):
    mono = _sine_burst(fx.SR, 1000.0, 0.030)
    stereo = np.column_stack((mono, 0.5 * mono))
    pa, pb = _prep(mono), _prep(stereo)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    cfg = PairComparisonConfig(blend_ratios=(0.5,))
    pair = PairComparisonResult(
        key_a=pa.key, key_b=pb.key, cfg=cfg, status=AnalysisStatus.OK,
        delay_samples=0.0, polarity=1,
    )
    attempts = {
        'pair': lambda: compare_pair(pa, pb, cfg),
        'prediction': lambda: predict_blend(pa, pb, cfg, alignment='suggested'),
        'blend': lambda: blend_sum(pa, pb, pair, ratio_b=0.5),
        'export': lambda: export_blend(pa, pb, pair, ratio_b=0.5,
                                       dest_dir=str(tmp_path)),
    }
    outcomes = {name: _reasoned_channel_rejection(call)
                for name, call in attempts.items()}

    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    assert (all(rejected for rejected, _ in outcomes.values()) and
            not list(tmp_path.glob('*.wav'))), outcomes


def test_fractional_shift_removes_known_delay():
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    true_delay = 40.0
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fx.SR)
    delayed = np.fft.irfft(X * np.exp(-2j * np.pi * f * true_delay / fx.SR), n)
    fixed = fractional_shift(delayed[96:], true_delay)
    # aligned tail matches the original tail
    corr = np.corrcoef(fixed[1000:8000], x[96 + 1000:96 + 8000])[0, 1]
    assert corr > 0.995, corr


def test_apply_alignment_applies_delay_and_polarity():
    x = fx.boxy_fixture(300.0, 0.02, n=24000)
    cfg = IRProcessingConfig(delay_samples=7.0, polarity=-1)
    out, warnings = apply_alignment(_prep(x), cfg)
    # output = polarity-flipped then advanced by 7 samples
    expected = fractional_shift(-x, 7.0)
    corr = np.corrcoef(out[500:8000, 0], expected[500:8000])[0, 1]
    assert corr > 0.999
    assert isinstance(warnings, list)


def test_round_trip_measure_then_fix_on_raw_windows():
    """Measure B's delay on raw windows, apply the fix, re-measure: ~0."""
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    true_delay = 40.0
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fx.SR)
    delayed = np.fft.irfft(X * np.exp(-2j * np.pi * f * true_delay / fx.SR), n)
    lo, hi = 96, 20000
    xa, xb = x[lo:hi], delayed[lo:hi]
    measured, _ = _estimate_delay(xa, xb, fx.SR, PairComparisonConfig())
    assert abs(measured - true_delay) <= 0.25, measured  # B delayed by +40

    fixed = fractional_shift(delayed[lo:hi], measured)   # advance by the measured delay
    remeasured, _ = _estimate_delay(xa, fixed[:len(xa)], fx.SR,
                                    PairComparisonConfig())
    assert abs(remeasured) <= 0.25, remeasured


def test_source_files_never_written(tmp_path):
    from app.core.analysis import analyze_file
    from app.extensions.adapters import LegacyIRAdapter
    from tests.synth import write_wav
    path = Path(write_wav(tmp_path / 'src.wav', fx.boxy_fixture(300.0, 0.05)))
    before = path.read_bytes()
    rec = analyze_file(str(path))
    prepared = LegacyIRAdapter().load_path(str(rec.path))
    prepared = prepare(prepared, PreprocessingConfig())
    cfg = IRProcessingConfig(delay_samples=12.0, polarity=-1)
    data, _ = apply_alignment(prepared, cfg)
    report = export_processed(prepared, cfg, str(tmp_path / 'out'))
    assert path.read_bytes() == before            # source immutable
    assert data is not prepared.data              # processed copy
    assert Path(report.output_path).exists()


def test_export_processed_wav_round_trip(tmp_path):
    from app.core.analysis import analyze_data
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    true_delay = 25.0
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fx.SR)
    delayed = np.fft.irfft(X * np.exp(-2j * np.pi * f * true_delay / fx.SR), n)
    pb = _prep(delayed)
    cfg = IRProcessingConfig(delay_samples=true_delay)    # advance back
    report = export_processed(pb, cfg, str(tmp_path / 'out'))
    data, sr = sf.read(report.output_path, always_2d=True)
    pair = compare_pair(_prep(x), _prep(data[:, 0]), PairComparisonConfig())
    # after onset alignment the residual must be ~0 (within parabolic tolerance)
    assert abs(pair.delay_samples) <= 1.0, pair.delay_samples
    assert pair.polarity == 1


def test_export_is_collision_safe_and_atomic(tmp_path):
    pb = _prep(fx.boxy_fixture(300.0, 0.02, n=24000))
    cfg = IRProcessingConfig()
    r1 = export_processed(pb, cfg, str(tmp_path))
    r2 = export_processed(pb, cfg, str(tmp_path))
    p1, p2 = Path(r1.output_path), Path(r2.output_path)
    assert p1 != p2 and p1.exists() and p2.exists()
    leftovers = list(tmp_path.glob('*.tmp'))
    assert not leftovers, leftovers


def test_blend_sum_aligns_b_and_mixes(tmp_path):
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    true_delay = 40.0
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fx.SR)
    delayed = np.fft.irfft(X * np.exp(-2j * np.pi * f * true_delay / fx.SR), n)
    pa, pb = _prep(x), _prep(delayed)
    from dataclasses import replace as dc_replace
    pair_obj = compare_pair(pa, pb, PairComparisonConfig())
    # the known ground-truth alignment: B must be advanced by 40 samples
    corrected = fractional_shift(delayed, true_delay)
    pair_known = dc_replace(pair_obj, delay_samples=true_delay, polarity=1)
    mix, sr, warnings = blend_sum(pa, pb, pair_known, 1.0)
    corr = np.corrcoef(mix[96 + 1000:96 + 8000, 0],
                       corrected[96 + 1000:96 + 8000])[0, 1]
    assert corr > 0.995, corr
    assert mix.shape[0] >= pa.frames


def test_blend_sum_uses_documented_linear_crossfade_weights():
    a = np.zeros(512)
    b = np.zeros(512)
    a[80:84] = (0.2, -0.7, 0.4, -0.1)
    b[80:84] = (-0.3, 0.5, 0.1, 0.6)
    pa, pb = _prep(a), _prep(b)
    assert pa.sample_rate == pb.sample_rate
    assert pa.status == pb.status == AnalysisStatus.OK
    pair = PairComparisonResult(
        key_a=pa.key, key_b=pb.key, cfg=PairComparisonConfig(),
        status=AnalysisStatus.OK, delay_samples=0.0, polarity=1,
    )
    a_before = pa.data.copy()
    b_before = pb.data.copy()

    mix_a, sr_a, warnings_a = blend_sum(pa, pb, pair, ratio_b=0.0)
    mix_mid, sr_mid, warnings_mid = blend_sum(pa, pb, pair, ratio_b=0.5)
    mix_b, sr_b, warnings_b = blend_sum(pa, pb, pair, ratio_b=1.0)

    a_oracle = np.zeros_like(mix_a)
    b_oracle = np.zeros_like(mix_a)
    a_oracle[:pa.frames] = a_before
    b_oracle[:pb.frames] = b_before
    np.testing.assert_allclose(mix_a, a_oracle, rtol=0, atol=1e-12)
    np.testing.assert_allclose(mix_mid, 0.5 * a_oracle + 0.5 * b_oracle,
                               rtol=0, atol=1e-12)
    np.testing.assert_allclose(mix_b, b_oracle, rtol=0, atol=1e-12)
    assert (sr_a, sr_mid, sr_b) == (pa.sample_rate,) * 3
    assert warnings_a == warnings_mid == warnings_b == []
    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)


def test_export_pair_aligned_b_mixed_rate_impulse(tmp_path):
    """48k A + physically-delayed 96k B: aligned export lands on the common
    (A) rate, peak-aligned within 2 samples, with full rate provenance."""
    a_sr, b_sr = 48000, 96000
    peak_a, phys_delay_a = 1000, 480          # frames at A's rate (10 ms)
    a = np.zeros(6000)
    a[peak_a] = 1.0
    b = np.zeros(2 * 6000)
    b[2 * (peak_a + phys_delay_a)] = 1.0      # same event, B arrives later
    pa, pb = _prep(a, a_sr), _prep(b, b_sr)
    pair = compare_pair(pa, pb, PairComparisonConfig())
    assert pair.status == AnalysisStatus.OK

    report = export_pair_aligned_b(pa, pb, pair, str(tmp_path))

    data, sr = sf.read(report.output_path, always_2d=True)
    assert sr == a_sr                          # A/common rate, not B's 96k
    peak = int(np.argmax(np.abs(data[:, 0])))
    assert abs(peak - peak_a) <= 2, peak       # physical alignment preserved
    assert report.source_key == pb.key
    assert report.applied['source_sample_rate_a_hz'] == a_sr
    assert report.applied['source_sample_rate_b_hz'] == b_sr
    assert report.applied['analysis_output_sample_rate_hz'] == a_sr
    assert any('resampled' in w for w in report.warnings)


def test_report_json_contains_provenance(tmp_path):
    a = fx.boxy_fixture(250.0, 0.02, n=24000)
    b = fx.boxy_fixture(280.0, 0.03, n=24000)
    pa, pb = _prep(a), _prep(b)
    cfg = PairComparisonConfig()
    pair = compare_pair(pa, pb, cfg)
    pred = predict_blend(pa, pb, cfg, alignment='suggested')
    report = export_pair_report(pair, pred, None, None, str(tmp_path))
    doc = json.loads(Path(report.output_path).read_text(encoding='utf-8'))
    assert doc['units']['delay_ms'] == 'ms'
    assert doc['pair']['polarity'] in (1, -1)
    assert 'signature_a' in doc['pair']
    assert 'blend' in doc and 'warnings' in doc
