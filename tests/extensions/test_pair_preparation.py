"""WP-04 pair_preparation contract: common-rate full buffers, source immutability."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                       PreprocessingConfig, SourceKey)
from app.extensions.pair_preparation import prepare_pair
from app.extensions.preprocessing import prepare
from tests.extensions import fixtures as fx


def _prep(x, sr=fx.SR):
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    arr = arr.copy()
    arr.setflags(write=False)
    return prepare(AudioBuffer(SourceKey('mem', 0, 0, sr, arr.shape[1]), arr),
                   PreprocessingConfig())


def test_same_rate_full_buffers_and_no_warnings():
    a = fx.boxy_fixture(300.0, 0.05, n=24000)
    b = fx.boxy_fixture(320.0, 0.05, n=24000)
    pa, pb = _prep(a), _prep(b)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    pair = prepare_pair(pa, pb)

    assert pair.status == AnalysisStatus.OK
    assert pair.sample_rate == pa.sample_rate == pb.sample_rate
    assert pair.warnings == ()
    # complete buffers are kept (leading silence preserved), never the source
    np.testing.assert_array_equal(pair.data_a, a_before)
    np.testing.assert_array_equal(pair.data_b, b_before)
    assert pair.data_a is not pa.data and pair.data_b is not pb.data
    assert pair.data_a.shape[0] == pa.frames
    assert pair.data_b.shape[0] == pb.frames
    assert pair.onset_a == pa.onset and pair.onset_b == pb.onset
    assert pair.tail_end_a == pa.tail_end and pair.tail_end_b == pb.tail_end
    assert pair.onset_delay_samples == pb.onset - pa.onset
    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)


def test_mixed_rate_b_resampled_with_scaled_index_and_warning():
    """B at 2x A's rate is physically resampled to A's rate, not relabeled."""
    x = fx.decay_fixture(150.0, 0.02, n=24000, delay_ms=2.0)
    pa = _prep(x, fx.SR)
    pb = _prep(x, fx.SR * 2)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    pair = prepare_pair(pa, pb)

    assert pair.status == AnalysisStatus.OK
    assert pair.sample_rate == pa.sample_rate
    assert pair.source_sample_rate_a == fx.SR
    assert pair.source_sample_rate_b == fx.SR * 2
    assert len(pair.warnings) == 1 and 'resampled' in pair.warnings[0]
    # B downsampled 2:1 -> about half the frames
    assert abs(len(pair.data_b) - pb.frames / 2) <= 2, len(pair.data_b)
    # onset/tail indices scale with the rate ratio (documented contract)
    assert pair.onset_b == round(pb.onset * fx.SR / (fx.SR * 2))
    assert pair.tail_end_b == round(pb.tail_end * fx.SR / (fx.SR * 2))
    # the physical peak position survives resampling
    peak_b = int(np.argmax(np.abs(pair.data_b[:, 0])))
    assert abs(peak_b - pb.peak_index / 2) <= 3, peak_b
    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)


def test_sources_never_modified_by_prepare_pair():
    """prepare_pair is read-only over both PreparedIR sources."""
    x = fx.boxy_fixture(300.0, 0.05, n=24000)
    pa = _prep(x, fx.SR)
    pb = _prep(x, fx.SR * 2)
    a_before = pa.data.copy()
    b_before = pb.data.copy()
    prepare_pair(pa, pb)
    prepare_pair(pb, pa)   # swapped order: B-rate A, A-rate B
    np.testing.assert_array_equal(pa.data, a_before)
    np.testing.assert_array_equal(pb.data, b_before)
    assert not pa.data.flags.writeable and not pb.data.flags.writeable


def test_incompatible_pairs_rejected_without_copies():
    from app.extensions.contracts import PairComparisonConfig
    from app.extensions.pair_compare import compare_pair
    mono = _prep(fx.decay_fixture(150.0, 0.02, n=24000))
    stereo = _prep(np.column_stack(
        (fx.decay_fixture(150.0, 0.02, n=24000),
         fx.decay_fixture(150.0, 0.02, n=24000))))
    pair = prepare_pair(mono, stereo)
    assert pair.status == AnalysisStatus.INCOMPATIBLE
    assert 'channel' in pair.reason
    result = compare_pair(mono, stereo, PairComparisonConfig())
    assert result.status == AnalysisStatus.INCOMPATIBLE