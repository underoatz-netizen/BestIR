# -*- coding: utf-8 -*-
"""Wave5 view tests: WaveformView, SpectrogramView, PhaseBlendView (offscreen).

Tests exercise the actual public APIs of the Wave5 views:
- WaveformView: show_envelopes / set_envelope_mode / set_zoom_mode (U05)
- SpectrogramView: show_pair(dyn=...) + the Show:/dB range selectors (U03)
- PhaseBlendView: show_blend, the alignment selector (U06) and the blend-ratio
  slider snap (40 % -> nearest cached ratio displayed as 50 %).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.extensions.contracts import (AnalysisStatus, AudioBuffer,  # noqa: E402
                                      EnvelopeConfig, PairComparisonConfig,
                                      PreprocessingConfig, SourceKey)
from app.extensions.preprocessing import prepare  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _synth_ir(n=4096, sr=48000):
    t = np.arange(n) / sr
    env = np.exp(-t * 8.0)
    x = np.sin(2 * np.pi * 440 * t) * env
    x[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr))
    return x.astype(np.float64)


def _prepared(name, data, sr=48000):
    samples = np.asarray(data, dtype=np.float64)[:, None].copy()
    samples.setflags(write=False)
    return prepare(
        AudioBuffer(SourceKey(name, 0, 0, sr, 1), samples),
        PreprocessingConfig(),
    )


class TestWaveformView:
    def test_switch_hilbert_rms_and_attack_zoom(self, qapp):
        from app.extensions.envelope import compute_envelope
        from app.extensions.ui.waveform_view import WaveformView

        sr = 48000
        x = _synth_ir(sr=sr)
        env = compute_envelope(_prepared('synth', x, sr), EnvelopeConfig())
        assert env.status == AnalysisStatus.OK
        view = WaveformView()
        # feed the envelope pair through the public plotting API
        view.show_envelopes(env, env)
        # switch envelope source Hilbert -> RMS (public U05 selector)
        view.set_envelope_mode("hilbert")
        assert view.envelope_mode() == "hilbert"
        view.set_envelope_mode("rms")
        assert view.envelope_mode() == "rms"
        # toggle attack zoom (public U05 zoom selector)
        view.set_zoom_mode("attack")
        assert view.zoom_mode() == "attack"
        view.set_zoom_mode("full")
        assert view.zoom_mode() == "full"
        view.close()


class TestSpectrogramView:
    def test_select_a_card_and_80db_range(self, qapp):
        from app.extensions.spectrogram import compute_spectrogram
        from app.extensions.contracts import TimeFrequencyConfig
        from app.extensions.ui.spectrogram_view import SpectrogramView
        from tests.extensions import fixtures as fx

        spec_a = compute_spectrogram(
            _prepared('a', fx.decay_fixture(300.0, 0.02, n=24000)),
            TimeFrequencyConfig())
        spec_b = compute_spectrogram(
            _prepared('b', fx.boxy_fixture(300.0, 0.08, n=24000)),
            TimeFrequencyConfig())
        assert spec_a.status == spec_b.status == AnalysisStatus.OK

        view = SpectrogramView()
        # 80 dB shared range via the public render API
        view.show_pair(spec_a, spec_b, dyn=80.0)
        assert view._last_dyn == 80.0
        import pyqtgraph as pg
        levels_a = tuple(float(v) for v in
                         next(i.getLevels() for i in
                              view._plots['A'].getPlotItem().items
                              if isinstance(i, pg.ImageItem)))
        assert levels_a[1] - levels_a[0] == pytest.approx(80.0)

        # "select a card": the Show selector hides the other panels
        # (isHidden() tracks the explicit visibility state even before the
        # top-level window itself is shown offscreen)
        view.view_selector.setCurrentIndex(view.view_selector.findData('A'))
        assert not view._cards['A'].isHidden()
        assert view._cards['B'].isHidden()
        assert view._cards['diff'].isHidden()
        view.view_selector.setCurrentIndex(view.view_selector.findData('all'))
        assert not view._cards['B'].isHidden()
        view.close()


class TestPhaseBlendView:
    def test_raw_alignment_and_slider_40_shows_50(self, qapp):
        from app.extensions.pair_compare import compare_pair, predict_blend
        from app.extensions.ui.phase_blend_view import PhaseBlendView
        from tests.extensions import fixtures as fx

        signal = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
        a = _prepared('a', signal)
        b = _prepared('b', -np.asarray(signal, dtype=np.float64))
        cfg = PairComparisonConfig(blend_ratios=(0.0, 0.5, 1.0))
        pair = compare_pair(a, b, cfg)
        blend = predict_blend(a, b, cfg, alignment='raw')
        assert pair.status == blend.status == AnalysisStatus.OK

        view = PhaseBlendView()
        view.show_blend(pair, blend)
        # raw alignment is present in the bundle -> combo reflects it
        assert view.alignment_combo.currentData() == 'raw'
        # toggling to a non-cached mode requests a recompute; back to 'raw'
        # is available so no request is emitted
        requested = []
        view.alignment_requested.connect(requested.append)
        view.alignment_combo.setCurrentIndex(
            view.alignment_combo.findData('suggested'))
        assert requested == ['suggested']
        view.alignment_combo.setCurrentIndex(
            view.alignment_combo.findData('raw'))
        assert requested == ['suggested']

        # slider 40 snaps to the nearest cached ratio (0.5) -> label shows 50%
        view.ratio_slider.setValue(40)
        assert view.ratio_slider.value() == 50
        assert '50% B' in view.ratio_label.text()
        view.close()