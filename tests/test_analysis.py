import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.analysis import analyze_data, analyze_file
from tests.synth import one_pole_lowpass_ir, synth_ir, write_wav


def test_dirac_is_flat():
    n, sr = 9600, 48000
    ir = np.zeros((n, 1))
    ir[int(0.001 * sr), 0] = 1.0
    res = analyze_data(ir, sr)
    assert res.flatness_db < 1.0
    assert abs(res.tilt_db_oct) < 0.3
    assert 'Flat' in res.tags
    assert res.channels == 1


def test_lowpass_reads_dark():
    sr = 48000
    ir = one_pole_lowpass_ir(1500, sr=sr)[:, None]
    res = analyze_data(ir, sr)
    assert res.tilt_db_oct < -1.0
    assert 'Dark' in res.tags
    assert 'Bright' not in res.tags


def test_highpass_reads_bright():
    sr = 48000
    lp = one_pole_lowpass_ir(1500, sr=sr)
    ir = (np.diff(lp, prepend=lp[0])[:, None])  # first difference = highpass
    res = analyze_data(ir, sr)
    assert res.tilt_db_oct > 1.0
    assert 'Bright' in res.tags
    assert 'Dark' not in res.tags


def test_scooped_shape_tags_and_bands():
    sr, n = 48000, 19200
    anchors = [-3, 0, 3, 2, -5, 2, 4, 1]  # mid dip at 1 kHz
    ir = synth_ir(sr=sr, n=n, anchors_db=anchors)
    res = analyze_data(ir, sr)
    assert res.band_levels['Mid'] < res.band_levels['Low'] - 2
    assert res.band_levels['Mid'] < res.band_levels['High'] - 2
    assert 'Scooped' in res.tags


def test_mid_forward_tag():
    sr, n = 48000, 19200
    anchors = [-4, -2, -1, 3, 4, 0, -2, -4]
    ir = synth_ir(sr=sr, n=n, anchors_db=anchors)
    res = analyze_data(ir, sr)
    assert res.band_levels['Mid'] > 2.0
    assert 'Mid-forward' in res.tags


def test_stereo_and_effective_length(tmp_path):
    sr, n = 48000, 24000  # 500 ms
    rng = np.random.default_rng(7)
    t = np.arange(n) / sr
    decay = np.exp(-t / 0.03)  # -60 dB at ~7*tau ~= 210 ms
    ir = np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1) * decay[:, None]
    ir[: int(0.002 * sr)] = 0.0  # silence before onset
    path = write_wav(tmp_path / 'st.wav', ir, sr)
    res = analyze_file(path)
    assert res.channels == 2
    assert res.sample_rate == sr
    assert 120.0 < res.effective_length_ms < 320.0


def test_broken_file_raises(tmp_path):
    bad = tmp_path / 'bad.wav'
    bad.write_bytes(b'not a wav')
    from app.core.audio_io import AudioLoadError
    with pytest.raises(AudioLoadError):
        analyze_file(str(bad))
