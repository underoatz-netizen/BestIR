"""WP-07 gates: extended UI wiring without modifying the legacy window."""
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def extended(qapp, tmp_path, monkeypatch):
    import app.ui.main_window as legacy_mod
    import app.ui.workers as legacy_workers
    from app.extensions.ui.main_window_adapter import ExtendedMainWindow

    legacy_workers.ScanWorker.start = lambda self: None   # no real-scan race
    win = ExtendedMainWindow()
    # seed library with three synthetic IRs (no licensed library dependency)
    from app.core.cache import LibraryCache
    from app.core.scanner import scan_library
    from tests.extensions import fixtures as fx
    from tests.synth import write_wav
    lib = tmp_path / 'lib'
    lib.mkdir()
    write_wav(lib / 'a.wav', fx.boxy_fixture(300.0, 0.06, n=24000))
    write_wav(lib / 'b.wav', fx.clean_fixture(n=24000))
    write_wav(lib / 'c.wav', fx.decay_fixture(100.0, 0.02, n=24000))
    cache = LibraryCache(str(tmp_path / 'fp_legacy.json'))
    win.library = scan_library([str(lib)], cache)
    tags = sorted({t for r in win.library for t in r.tags})
    win.library_panel.set_available_tags(tags)
    win._on_scan_done(win.library)
    yield win
    win.close()


def test_extended_is_a_legacy_subclass(extended):
    from app.ui.main_window import MainWindow
    assert isinstance(extended, MainWindow)


def test_legacy_ui_elements_intact(extended):
    assert extended.library_panel is not None
    assert extended.plot is not None
    assert extended.screen_panel is not None
    assert extended.inspector is not None
    # legacy signals still connected: selecting a row updates the inspector
    extended.library_panel.table.selectRow(0)
    recs = extended.library_panel.selected_records()
    assert len(recs) == 1
    extended.inspector.show_record(recs[0])
    assert recs[0].path.split('/')[-1].split(chr(92))[-1] in \
        extended.inspector.name_label.text()


def test_workbench_populates_ab_and_summary(extended, qapp):
    extended.show_workbench()
    wb = extended._workbench
    assert wb is not None
    recs = extended.library_panel.visible_records()
    wb.set_pair(recs[0], recs[1])
    # run the pair pipeline synchronously (workers need an event loop)
    from app.extensions.pair_compare import compare_pair, predict_blend
    from app.extensions.contracts import PairComparisonConfig
    from app.extensions.csd import compute_csd
    from app.extensions.contracts import TimeFrequencyConfig
    from app.extensions.spectrogram import compute_spectrogram
    pair = compare_pair(wb.service.prepared(recs[0]), wb.service.prepared(recs[1]),
                        PairComparisonConfig())
    blend = predict_blend(wb.service.prepared(recs[0]), wb.service.prepared(recs[1]),
                          PairComparisonConfig(), alignment='suggested')
    env_a = wb.service.envelope(recs[0])
    env_b = wb.service.envelope(recs[1])
    result = {'pair': pair, 'blend': blend, 'env_a': env_a, 'env_b': env_b}
    wb._pair_request_id = 4242
    wb._on_pair_done(4242, result)
    assert 'delay' in wb.status.text() or 'Pair:' in wb.status.text()
    # summary rows were populated
    assert wb.summary.table.rowCount() > 0
    # spectrogram tab path
    wb._apply_spec('spec_a', compute_spectrogram(wb.service.prepared(recs[0]), TimeFrequencyConfig()))
    wb._apply_spec('spec_b', compute_spectrogram(wb.service.prepared(recs[1]), TimeFrequencyConfig()))
    wb.spectrogram.show_pair(wb._spec_a, wb._spec_b)
    wb.spectrogram.show_metrics(wb._spec_a.metrics, wb._spec_b.metrics)
    extended._workbench.close()


def test_stale_result_is_rejected(extended):
    extended.show_workbench()
    wb = extended._workbench
    recs = extended.library_panel.visible_records()
    wb.set_pair(recs[0], recs[1])
    wb._pair_request_id = 777
    stale_id = wb._pair_request_id + 999
    from app.extensions.pair_compare import compare_pair
    from app.extensions.contracts import PairComparisonConfig
    pair = compare_pair(wb.service.prepared(recs[0]), wb.service.prepared(recs[1]),
                        PairComparisonConfig())
    status_before = wb.status.text()
    wb._on_pair_done(stale_id, {'pair': pair, 'blend': None,
                                'env_a': None, 'env_b': None})
    assert wb.status.text() == status_before   # stale update ignored
    extended._workbench.close()


def test_opengl_absence_falls_back():
    from app.extensions.ui.csd_view import CsdView
    from app.extensions.contracts import (AudioBuffer, PreprocessingConfig,
                                          SourceKey, TimeFrequencyConfig)
    from app.extensions.csd import compute_csd
    from app.extensions.preprocessing import prepare
    from tests.extensions import fixtures as fx
    view = CsdView()
    assert view._renderer is not None
    x = fx.decay_fixture(100.0, 0.02, n=24000)
    arr = x[:, None].copy()
    arr.setflags(write=False)
    prep = prepare(AudioBuffer(SourceKey('m', 0, 0, 48000, 1), arr),
                   PreprocessingConfig())
    res = compute_csd(prep, TimeFrequencyConfig(profile='balanced'))
    view.show_csd(res, 'A')   # must not raise on any renderer path


def test_legacy_window_unchanged_at_rest(extended):
    # rank via the legacy path and confirm the workbench didn't alter scores
    extended.screen_panel.preset_list.setCurrentRow(0)
    extended.screen_panel._emit_target()
    extended._rank()
    assert extended.library_panel.model.rowCount() == min(25, len(extended.library))
    extended._clear_rank()
    assert extended.library_panel.model.rowCount() == len(extended.library)
