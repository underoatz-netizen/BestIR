"""WP-08 gates: non-destructive processing, collision-safe export, provenance."""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AudioBuffer, IRProcessingConfig,
                                      PairComparisonConfig, PreprocessingConfig,
                                      SourceKey)
from app.extensions.pair_compare import _estimate_delay, compare_pair, predict_blend
from app.extensions.preprocessing import prepare
from app.extensions.processing import apply_alignment, blend_sum, fractional_shift
from app.extensions.processing_export import (export_blend, export_pair_report,
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
    cfg = IRProcessingConfig(delay_samples=-true_delay)   # advance back
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
