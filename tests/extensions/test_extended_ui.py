"""WP-07 gates: extended UI wiring without modifying the legacy window."""
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402


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


def test_b07_invalid_b_spectrogram_and_blend_surface_no_data(qapp):
    from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                          PairComparisonConfig,
                                          PreprocessingConfig, SourceKey,
                                          TimeFrequencyConfig)
    from app.extensions.pair_compare import compare_pair, predict_blend
    from app.extensions.preprocessing import prepare
    from app.extensions.spectrogram import compute_spectrogram
    from app.extensions.ui.phase_blend_view import PhaseBlendView
    from app.extensions.ui.spectrogram_view import SpectrogramView
    from tests.extensions import fixtures as fx

    def prepared(name, data):
        samples = np.asarray(data, dtype=np.float64)[:, None].copy()
        samples.setflags(write=False)
        return prepare(
            AudioBuffer(SourceKey(name, 0, 0, fx.SR, 1), samples),
            PreprocessingConfig(),
        )

    valid = prepared('valid', fx.decay_fixture(150.0, 0.02, n=24000))
    silent = prepared('silent', fx.silent())
    cfg = PairComparisonConfig()
    spec_a = compute_spectrogram(valid, TimeFrequencyConfig())
    spec_b = compute_spectrogram(silent, TimeFrequencyConfig())
    pair = compare_pair(valid, silent, cfg)
    blend = predict_blend(valid, silent, cfg, alignment='suggested')

    assert spec_a.status == AnalysisStatus.OK
    assert spec_b.status == AnalysisStatus.SILENT
    assert spec_b.magnitude_db is None
    assert pair.status == blend.status == AnalysisStatus.SILENT

    spectrogram = SpectrogramView()
    spectrogram.show_pair(spec_a, spec_b)
    visible_text = ' '.join(
        label.text().lower() for label in spectrogram.findChildren(QLabel)
    )
    assert 'silent' in visible_text
    assert any(marker in visible_text for marker in
               ('no data', 'unavailable', 'invalid'))

    phase_blend = PhaseBlendView()
    phase_blend.show_blend(pair, blend)
    comb_text = phase_blend.comb_chip.text().lower()
    assert not any(label in comb_text for label in ('safe', 'low'))
    assert any(marker in comb_text for marker in
               ('no data', 'unavailable', 'invalid', 'n/a'))


def test_b04_phase_blend_chip_tracks_active_slider_ratio(qapp):
    from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                          PairComparisonConfig,
                                          PreprocessingConfig, SourceKey)
    from app.extensions.pair_compare import compare_pair, predict_blend
    from app.extensions.preprocessing import prepare
    from app.extensions.ui.phase_blend_view import PhaseBlendView
    from tests.extensions import fixtures as fx

    def prepared(name, data):
        samples = np.asarray(data, dtype=np.float64)[:, None].copy()
        samples.setflags(write=False)
        return prepare(
            AudioBuffer(SourceKey(name, 0, 0, fx.SR, 1), samples),
            PreprocessingConfig(),
        )

    signal = fx.decay_fixture(100.0, 0.02, n=24000, delay_ms=2.0)
    a, b = prepared('a', signal), prepared('inverted-b', -signal)
    cfg = PairComparisonConfig(blend_ratios=(0.0, 0.5, 1.0))
    pair = compare_pair(a, b, cfg)
    blend = predict_blend(a, b, cfg, alignment='raw')
    assert pair.status == blend.status == AnalysisStatus.OK

    view = PhaseBlendView()
    view.show_blend(pair, blend)
    view.ratio_slider.setValue(0)
    qapp.processEvents()
    view.ratio_slider.setValue(50)
    qapp.processEvents()

    cancellation_text = view.comb_chip.text().lower()
    assert '50% B' in view.ratio_label.text()
    assert not any(label in cancellation_text for label in ('safe', 'low'))
    assert any(label in cancellation_text for label in ('high', 'medium', 'error'))

    view.ratio_slider.setValue(0)
    qapp.processEvents()
    endpoint_text = view.comb_chip.text().lower()
    assert '0% B' in view.ratio_label.text()
    assert any(label in endpoint_text for label in ('safe', 'low'))
    assert endpoint_text != cancellation_text


def test_b04_valid_blend_without_reliable_bins_is_unknown(qapp):
    from app.extensions.contracts import (AnalysisStatus, AudioBuffer,
                                          PairComparisonConfig,
                                          PreprocessingConfig, SourceKey)
    from app.extensions.pair_compare import compare_pair, predict_blend
    from app.extensions.preprocessing import prepare
    from app.extensions.ui.phase_blend_view import PhaseBlendView
    from tests.extensions import fixtures as fx

    samples = fx.decay_fixture(150.0, 0.02, n=24000)[:, None].copy()
    samples.setflags(write=False)
    prepared = prepare(
        AudioBuffer(SourceKey('valid', 0, 0, fx.SR, 1), samples),
        PreprocessingConfig(),
    )
    safe_cfg = PairComparisonConfig(blend_ratios=(0.0, 0.5, 1.0))
    no_bins_cfg = PairComparisonConfig(
        blend_ratios=(0.0, 0.5, 1.0), risk_band=(float(fx.SR), float(2 * fx.SR)),
    )
    pair = compare_pair(prepared, prepared, safe_cfg)
    safe_blend = predict_blend(prepared, prepared, safe_cfg, alignment='raw')
    no_bins_blend = predict_blend(prepared, prepared, no_bins_cfg,
                                  alignment='raw')
    assert pair.status == safe_blend.status == no_bins_blend.status == AnalysisStatus.OK
    assert no_bins_blend.magnitude_db is not None
    assert no_bins_blend.worst_cancellation_db is None

    view = PhaseBlendView()
    view.show_blend(pair, safe_blend)
    assert any(label in view.comb_chip.text().lower() for label in ('safe', 'low'))
    view.show_blend(pair, no_bins_blend)
    qapp.processEvents()

    no_data_text = view.comb_chip.text().lower()
    assert any(marker in no_data_text for marker in
               ('no data', 'unknown', 'unavailable', 'n/a'))
    assert not any(label in no_data_text for label in ('safe', 'low'))


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


def _pair_bundle(workbench, rec_a, rec_b):
    from app.extensions.contracts import PairComparisonConfig
    from app.extensions.pair_compare import compare_pair, predict_blend

    cfg = PairComparisonConfig()
    prepared_a = workbench.service.prepared(rec_a)
    prepared_b = workbench.service.prepared(rec_b)
    return {
        'pair': compare_pair(prepared_a, prepared_b, cfg),
        'blend': predict_blend(prepared_a, prepared_b, cfg,
                               alignment='suggested'),
        'env_a': None,
        'env_b': None,
    }


def _run_queued_callback(qapp, callback):
    delivered = []

    def deliver():
        delivered.append(True)
        callback()

    QTimer.singleShot(0, deliver)
    qapp.processEvents()
    assert delivered == [True]


def _export_buttons_enabled(workbench):
    view = workbench.phase_blend
    return tuple(button.isEnabled() for button in
                 (view.btn_export_b, view.btn_export_blend,
                  view.btn_export_report))


def test_b06_selection_ignores_queued_old_success_before_debounce(extended,
                                                                    qapp):
    """A queued A/B success cannot revive results after B changes to C."""
    extended.show_workbench()
    wb = extended._workbench
    a, b, c = extended.library_panel.visible_records()
    old_bundle = _pair_bundle(wb, a, b)
    try:
        wb.set_pair(a, b)
        old_request_id = 8601
        wb._pair_request_id = old_request_id
        # Seed completed A/B state so invalidation must revoke export eligibility.
        wb._last_pair = old_bundle['pair']
        wb._last_blend = old_bundle['blend']
        wb.phase_blend.set_export_enabled(True)

        wb.set_b(c)
        state_after_selection = (wb._last_pair, wb._last_blend,
                                 _export_buttons_enabled(wb))
        new_status = wb.status.text()
        summary_rows = wb.summary.table.rowCount()
        callback_while_debouncing = []

        def deliver_old_success():
            callback_while_debouncing.append(wb._debounce.isActive())
            wb._on_pair_done(old_request_id, old_bundle)

        _run_queued_callback(qapp, deliver_old_success)

        assert callback_while_debouncing == [True]
        assert state_after_selection == (None, None, (False, False, False))
        assert wb._last_pair is None
        assert wb._last_blend is None
        assert _export_buttons_enabled(wb) == (False, False, False)
        assert wb.status.text() == new_status
        assert wb.summary.table.rowCount() == summary_rows
        assert wb.phase_blend._pair_result is None
        assert wb.phase_blend._blend_result is None
    finally:
        wb._debounce.stop()
        wb.close()


def test_b06_queued_old_failure_keeps_new_selection_analyzing(extended, qapp):
    """A queued A/B failure cannot replace the A/C analyzing status."""
    extended.show_workbench()
    wb = extended._workbench
    a, b, c = extended.library_panel.visible_records()
    try:
        wb.set_pair(a, b)
        old_request_id = 8602
        wb._pair_request_id = old_request_id

        wb.set_b(c)
        new_status = wb.status.text()
        callback_while_debouncing = []

        def deliver_old_failure():
            callback_while_debouncing.append(wb._debounce.isActive())
            wb._on_pair_failed(old_request_id, 'old A/B failure')

        _run_queued_callback(qapp, deliver_old_failure)

        assert callback_while_debouncing == [True]
        assert wb.status.text() == new_status
        assert 'analyzing' in wb.status.text().lower()
    finally:
        wb._debounce.stop()
        wb.close()


def test_b06_current_looking_id_rejects_wrong_pair_identity(extended, qapp):
    """Matching IDs are insufficient when callback sources are from A/B, not A/C."""
    extended.show_workbench()
    wb = extended._workbench
    a, b, c = extended.library_panel.visible_records()
    old_bundle = _pair_bundle(wb, a, b)
    try:
        wb.set_pair(a, c)
        callback_id = 8603
        wb._pair_request_id = callback_id
        current_b_key = wb.service.prepared(c).key
        assert old_bundle['pair'].key_b != current_b_key
        assert old_bundle['blend'].key_b != current_b_key
        new_status = wb.status.text()
        summary_rows = wb.summary.table.rowCount()
        callback_while_debouncing = []

        def deliver_wrong_pair():
            callback_while_debouncing.append(wb._debounce.isActive())
            wb._on_pair_done(callback_id, old_bundle)

        _run_queued_callback(qapp, deliver_wrong_pair)

        assert callback_while_debouncing == [True]
        assert wb._last_pair is None
        assert wb._last_blend is None
        assert wb.status.text() == new_status
        assert wb.summary.table.rowCount() == summary_rows
        assert wb.phase_blend._pair_result is None
    finally:
        wb._debounce.stop()
        wb.close()


def test_b06_queued_lazy_results_do_not_render_or_cache_old_b(extended, qapp):
    """Old B CSD/spectrogram callbacks cannot populate an A/C workbench."""
    from app.extensions.contracts import TimeFrequencyConfig
    from app.extensions.csd import compute_csd
    from app.extensions.spectrogram import compute_spectrogram

    class PendingSpecWorker:
        def __init__(self, request_id):
            self.request_id = request_id
            self.cancelled = False

        def isRunning(self):
            return not self.cancelled

        def cancel(self):
            self.cancelled = True

    extended.show_workbench()
    wb = extended._workbench
    a, b, c = extended.library_panel.visible_records()
    tf = TimeFrequencyConfig(profile='balanced')
    old_csd = compute_csd(wb.service.prepared(b), tf)
    old_spec = compute_spectrogram(wb.service.prepared(b), tf)
    current_spec_a = compute_spectrogram(wb.service.prepared(a), tf)
    try:
        wb.set_pair(a, b)
        csd_request_id, spec_request_id = 8604, 8605
        wb._spec_workers = {
            'csd_b': PendingSpecWorker(csd_request_id),
            'spec_b': PendingSpecWorker(spec_request_id),
        }

        wb.set_b(c)
        current_b_key = wb.service.prepared(c).key
        assert old_csd.key != current_b_key
        assert old_spec.key != current_b_key
        # A is valid for the new pair, so an old B would otherwise render A/B.
        wb._spec_a = current_spec_a
        wb._spec_results = {'a': current_spec_a}
        csd_items = tuple(id(item) for item in wb.csd._plot.getPlotItem().items)
        spec_items = {
            name: tuple(id(item) for item in plot.getPlotItem().items)
            for name, plot in wb.spectrogram._plots.items()
        }
        diff_text = wb.spectrogram._diff_label.text()
        callback_while_debouncing = []

        def deliver_old_lazy_results():
            callback_while_debouncing.append(wb._debounce.isActive())
            wb._on_spec_done('csd_b', csd_request_id, old_csd)
            wb._on_spec_done('spec_b', spec_request_id, old_spec)

        _run_queued_callback(qapp, deliver_old_lazy_results)

        assert callback_while_debouncing == [True]
        assert 'csd_b' not in wb._spec_cache
        assert 'spec_b' not in wb._spec_cache
        assert getattr(wb, '_csd_results', {}).get('b') is not old_csd
        assert getattr(wb, '_spec_results', {}).get('b') is not old_spec
        assert getattr(wb, '_spec_b', None) is not old_spec
        assert tuple(id(item) for item in wb.csd._plot.getPlotItem().items) == csd_items
        assert {
            name: tuple(id(item) for item in plot.getPlotItem().items)
            for name, plot in wb.spectrogram._plots.items()
        } == spec_items
        assert wb.spectrogram._diff_label.text() == diff_text
    finally:
        wb._debounce.stop()
        wb.close()


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


def _pump_until(qapp, predicate, timeout_ms=20000):
    """Spin the real Qt event loop (debounce timers + worker threads) until
    predicate() holds. Returns the final predicate value."""
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return bool(predicate())


def _click_through_event_loop(qapp, button):
    """Deliver a real button click via the Qt event loop (queued invocation),
    never by calling workbench handlers directly."""
    QTimer.singleShot(0, button.click)
    qapp.processEvents()


def _export_buttons(view):
    return (view.btn_export_b, view.btn_export_blend, view.btn_export_report)


def test_b17_pair_callback_renders_worker_results_only(extended, qapp):
    """B17 gate: fingerprint/phase/preparation run inside PairAnalysisWorker;
    the GUI pair callback only renders the worker-provided bundle."""
    import threading
    from unittest.mock import patch

    extended.show_workbench()
    wb = extended._workbench
    a, b = extended.library_panel.visible_records()[:2]
    main_tid = threading.get_ident()
    calls = {'fingerprint': [], 'phase': [], 'prepared': []}
    real_fp = wb.service.fingerprint
    real_phase = wb.service.phase
    real_prepared = wb.service.prepared

    def spy_fingerprint(record, force=False):
        calls['fingerprint'].append(threading.get_ident())
        return real_fp(record, force=force)

    def spy_phase(record, cfg=None):
        calls['phase'].append(threading.get_ident())
        return real_phase(record, cfg=cfg)

    def spy_prepared(record):
        calls['prepared'].append(threading.get_ident())
        return real_prepared(record)

    try:
        with patch.object(wb.service, 'fingerprint', spy_fingerprint), \
                patch.object(wb.service, 'phase', spy_phase), \
                patch.object(wb.service, 'prepared', spy_prepared):
            wb.set_pair(a, b)
            # real event loop: 250 ms debounce -> PairAnalysisWorker thread ->
            # queued finished_ok -> _on_pair_done (render only)
            assert _pump_until(
                qapp,
                lambda: wb._last_pair is not None
                        and wb.summary.table.rowCount() > 0), \
                'real pair pipeline never delivered a worker bundle'

        assert calls['fingerprint'], 'worker never computed fingerprints'
        assert calls['phase'], 'worker never computed phase'
        # heavyweight service work happened exclusively off the GUI thread
        assert all(tid != main_tid for tid in calls['fingerprint']), \
            f'fingerprint ran on GUI thread: {calls["fingerprint"]}'
        assert all(tid != main_tid for tid in calls['phase']), \
            f'phase ran on GUI thread: {calls["phase"]}'
        assert all(tid != main_tid for tid in calls['prepared']), \
            f'prepared ran on GUI thread: {calls["prepared"]}'
        # the GUI callback rendered the worker-provided results
        assert wb._last_pair is not None
        assert wb._last_fp_a is not None and wb._last_fp_b is not None
        assert wb.summary.table.rowCount() > 0
        assert wb.phase_blend._cache_a is not None
        assert wb.phase_blend._cache_b is not None
    finally:
        wb._debounce.stop()
        wb.close()


def test_b05_export_buttons_open_dialog_once_when_valid(extended, qapp,
                                                        tmp_path):
    """B05 gate: after the real worker pipeline completes, each export button
    click opens the directory dialog exactly once and writes a new output."""
    import hashlib
    from unittest.mock import Mock, patch
    import soundfile as sf

    extended.show_workbench()
    wb = extended._workbench
    a, b = extended.library_panel.visible_records()[:2]
    src_digests = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                   for p in (a.path, b.path)}
    try:
        wb.set_pair(a, b)
        # real pipeline: 250 ms debounce -> PairAnalysisWorker thread ->
        # queued finished_ok -> _on_pair_done enables exports
        assert _pump_until(qapp, lambda: wb.phase_blend.btn_export_b.isEnabled()), \
            'exports never became enabled for a fresh valid pair'

        out_dir = tmp_path / 'b05_export'
        out_dir.mkdir()
        dialog = Mock(return_value=str(out_dir))
        with patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory',
                   new=dialog):
            for idx, button in enumerate(_export_buttons(wb.phase_blend)):
                _click_through_event_loop(qapp, button)
                assert dialog.call_count == idx + 1, \
                    f'{button.text()} did not trigger the dialog exactly once'
                assert dialog.call_args_list[idx][0][0] is wb  # raised by workbench

        names = sorted(p.name for p in out_dir.iterdir())
        assert sum('aligned' in n for n in names) == 1, names
        assert sum('pct B' in n for n in names) == 1, names
        assert sum(n.endswith('.json') for n in names) == 1, names
        # reopen every artifact (gate: new output is readable)
        for name in names:
            p = out_dir / name
            if name.endswith('.json'):
                assert '"pair"' in p.read_text(encoding='utf-8')
            else:
                data, sr = sf.read(str(p))
                assert sr > 0 and len(data) > 0

        # cancel path: dialog dismissed -> no handler work, no new files
        with patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory',
                   new=Mock(return_value='')):
            _click_through_event_loop(qapp, wb.phase_blend.btn_export_b)
        assert sorted(p.name for p in out_dir.iterdir()) == names

        # sources untouched by the whole flow
        for p, digest in src_digests.items():
            assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
    finally:
        wb._debounce.stop()
        wb.close()


def test_b05_export_blocked_when_pair_missing_or_pending(extended, qapp,
                                                         tmp_path):
    """B05 gate: initial/analyzing/invalid states must not reach a dialog —
    neither through real clicks nor through a direct signal emission."""
    from unittest.mock import Mock, patch

    extended.show_workbench()
    wb = extended._workbench
    a, b = extended.library_panel.visible_records()[:2]
    out_dir = tmp_path / 'b05_blocked'   # deliberately not created
    dialog = Mock(return_value=str(out_dir))
    try:
        assert _export_buttons_enabled(wb) == (False, False, False)
        with patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory',
                   new=dialog):
            for button in _export_buttons(wb.phase_blend):
                _click_through_event_loop(qapp, button)
            # a single-slot selection has no pair: clicks and even a
            # programmatic emit must be refused by the handler guard
            wb.set_a(a)
            for button in _export_buttons(wb.phase_blend):
                _click_through_event_loop(qapp, button)
                button.click()
            for signal in (wb.phase_blend.export_aligned_b,
                           wb.phase_blend.export_blend,
                           wb.phase_blend.export_report):
                signal.emit()
            assert dialog.call_count == 0

            # waiting state: pair chosen but debounce/worker still pending
            wb.set_pair(a, b)
            assert _export_buttons_enabled(wb) == (False, False, False)
            for button in _export_buttons(wb.phase_blend):
                _click_through_event_loop(qapp, button)
            assert dialog.call_count == 0
            assert wb._export_ready() is False
        assert not out_dir.exists()
    finally:
        wb._debounce.stop()
        wb.close()


def test_b05_export_blocked_once_pair_becomes_stale(extended, qapp, tmp_path):
    """B05 gate: changing B right after a completed A/B export revokes the
    buttons instantly; stale clicks and stale emits open no dialog."""
    from unittest.mock import Mock, patch

    extended.show_workbench()
    wb = extended._workbench
    a, b, c = extended.library_panel.visible_records()
    out_dir = tmp_path / 'b05_stale'
    out_dir.mkdir()
    dialog = Mock(return_value=str(out_dir))
    try:
        wb.set_pair(a, b)
        assert _pump_until(qapp, lambda: wb.phase_blend.btn_export_b.isEnabled())
        with patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory',
                   new=dialog):
            _click_through_event_loop(qapp, wb.phase_blend.btn_export_b)
            assert dialog.call_count == 1
            assert any(p.name for p in out_dir.iterdir())
            written = set(out_dir.iterdir())

            # B changes to C: invalidation is synchronous — before the new
            # pair result exists, nothing may export
            wb.set_b(c)
            assert wb._export_ready() is False
            assert _export_buttons_enabled(wb) == (False, False, False)
            for button in _export_buttons(wb.phase_blend):
                _click_through_event_loop(qapp, button)
                assert dialog.call_count == 1
            for signal in (wb.phase_blend.export_aligned_b,
                           wb.phase_blend.export_blend,
                           wb.phase_blend.export_report):
                signal.emit()
            assert dialog.call_count == 1
            assert set(out_dir.iterdir()) == written   # no stale artifacts
    finally:
        wb._debounce.stop()
        wb.close()


def test_legacy_window_unchanged_at_rest(extended):
    # rank via the legacy path and confirm the workbench didn't alter scores
    extended.screen_panel.preset_list.setCurrentRow(0)
    extended.screen_panel._emit_target()
    extended._rank()
    assert extended.library_panel.model.rowCount() == min(25, len(extended.library))
    extended._clear_rank()
    assert extended.library_panel.model.rowCount() == len(extended.library)


def test_workbench_export_flow_writes_files(extended, tmp_path, qapp):
    """WP-08 UI path: pair done -> export aligned B / blend / report."""
    extended.show_workbench()
    wb = extended._workbench
    recs = extended.library_panel.visible_records()
    wb.set_pair(recs[0], recs[1])
    from app.extensions.contracts import PairComparisonConfig
    from app.extensions.pair_compare import compare_pair, predict_blend
    pair = compare_pair(wb.service.prepared(recs[0]),
                        wb.service.prepared(recs[1]), PairComparisonConfig())
    blend = predict_blend(wb.service.prepared(recs[0]),
                          wb.service.prepared(recs[1]), PairComparisonConfig(),
                          alignment='suggested')
    wb._pair_request_id = 7
    wb._on_pair_done(7, {'pair': pair, 'blend': blend,
                         'env_a': wb.service.envelope(recs[0]),
                         'env_b': wb.service.envelope(recs[1])})
    assert wb.phase_blend.btn_export_b.isEnabled()

    out_dir = tmp_path / 'exported'
    monkey_fx = QFileDialog_stub(out_dir)
    from unittest.mock import patch
    with patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory',
               return_value=str(out_dir)):
        wb._export_aligned_b()
        wb._export_blend()
        wb._export_report()
    files = sorted(p.name for p in out_dir.iterdir())
    assert any('aligned' in f for f in files), files
    assert any('pct B' in f for f in files), files
    assert any(f.endswith('.json') for f in files), files
    # sources untouched
    assert recs[0].path and Path(recs[0].path).exists()


class QFileDialog_stub:
    """Context shim so the test above reads clearly."""
    def __init__(self, out_dir):
        self.out_dir = out_dir

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---- B08: response targets survive presets and reach the ranking job -------
class _NoopSignal:
    def connect(self, callback):
        pass


class _SyncWorker:
    """Drop-in for AnalysisWorker: runs the queued job immediately with a
    cooperative-cancel stub, so target forwarding is asserted without
    threads or timing (the job is pure data plumbing, not worker logic)."""
    finished_ok = _NoopSignal()
    failed = _NoopSignal()
    request_id = -1

    def __init__(self, job, parent=None):
        self._job = job

    def start(self):
        import types
        self._job(types.SimpleNamespace(cancelled=False))


def test_b08_preset_state_roundtrip_keeps_targets(qapp):
    import json
    from app.extensions.ui.response_search_panel import (PRESETS,
                                                         ResponseSearchPanel)

    panel = ResponseSearchPanel()
    for name, (_w, _c, targets) in PRESETS.items():
        panel._preset_btns[name].click()
        state = panel.get_preset_state()
        # oracle: the named preset's own target dict (production data)
        assert state['targets'] == targets, name
        saved = json.loads(json.dumps(state))   # save/load via JSON
        assert saved == state, name
        # switching away clears targets; restoring the snapshot brings them back
        panel._preset_btns['Custom'].click()
        assert panel.get_preset_state()['targets'] == {}
        panel.apply_preset_state(saved)
        restored = panel.get_preset_state()
        assert restored['targets'] == targets, name
        assert restored['name'] == name
        assert restored['weights'] == state['weights']


def test_b08_emitted_request_carries_current_targets(qapp):
    from app.extensions.ui.response_search_panel import (PRESETS,
                                                         ResponseSearchPanel)

    panel = ResponseSearchPanel()
    requests = []
    panel.rank_requested.connect(requests.append)

    panel._preset_btns['Fast Attack'].click()
    panel.go_btn.click()
    assert requests, 'go button emitted no request'
    request = requests[-1]
    assert request.get('targets') == PRESETS['Fast Attack'][2]
    # emitted snapshot must not alias the panel's internal state
    request['targets']['attack'] = 99.0
    assert panel.get_preset_state()['targets'] == {'attack': 1.5}

    panel._preset_btns['Custom'].click()
    panel.go_btn.click()
    assert requests[-1].get('targets') == {}
    panel.spin_gd.setValue(1.0)   # user tweak keeps (empty) targets present
    panel.go_btn.click()
    assert requests[-1]['targets'] == {}
    assert requests[-1]['weights']['gd_spread'] == 1.0


def test_b08_workbench_search_job_forwards_targets(extended, qapp,
                                                   monkeypatch):
    import app.extensions.advanced_matching as am_mod
    import app.extensions.ui.compare_workbench as wb_mod

    extended.show_workbench()
    wb = extended._workbench
    seen = {}

    def spy_rank(records, fps, service, target, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(wb_mod, 'AnalysisWorker', _SyncWorker)
    monkeypatch.setattr(am_mod, 'rank_by_response', spy_rank)
    monkeypatch.setattr(wb.service, 'fingerprint', lambda rec: None)

    request = {'weights': {'tone': 1.0, 'd20': 1.5},
               'constraints': {'max_tone_db': 3.0},
               'targets': {'d20': 25.0},
               'policy': 'exclude'}
    try:
        wb._run_response_search(request)
    finally:
        wb._debounce.stop()
        wb.close()
    assert seen, 'rank_by_response never called by the workbench search job'
    assert seen.get('targets') is request['targets']


def test_b08_main_window_search_job_forwards_targets(extended, qapp,
                                                     monkeypatch):
    import app.extensions.advanced_matching as am_mod
    import app.extensions.ui.main_window_adapter as mw_mod

    seen = {}

    def spy_rank(records, fps, service, target, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(mw_mod, 'AnalysisWorker', _SyncWorker)
    monkeypatch.setattr(am_mod, 'rank_by_response', spy_rank)
    monkeypatch.setattr(extended.response_service, 'fingerprint',
                        lambda rec: None)

    request = {'weights': {'tone': 1.0, 'boxiness': 1.5},
               'constraints': {'max_tone_db': 6.0},
               'targets': {'boxiness': 0.0, 'gd_spread': 0.5},
               'policy': 'reject'}
    extended._run_search(request)
    assert seen, 'rank_by_response never called by the window search job'
    assert seen.get('targets') is request['targets']
