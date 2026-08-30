"""Extended offscreen GUI smoke test (WP-07/WP-09).

Runs the extended application headlessly: workbench opens, A/B populate from
the library, all tabs initialize, response search ranks candidates — no audio
devices required. Also asserts the legacy window still works via the subclass.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    # the seeded QSettings folder would start a real background scan that
    # races this test's synthetic library — stub the worker for determinism
    import app.ui.workers as legacy_workers
    legacy_workers.ScanWorker.start = lambda self: None

    from app.core.cache import LibraryCache
    from app.core.scanner import scan_library
    from app.extensions.ui.main_window_adapter import ExtendedMainWindow
    from tests.extensions import fixtures as fx
    from tests.synth import write_wav

    win = ExtendedMainWindow()
    lib = Path(tempfile.mkdtemp(prefix='bestir_ext_lib'))
    write_wav(lib / 'boxy.wav', fx.boxy_fixture(300.0, 0.06, n=48000))
    write_wav(lib / 'clean.wav', fx.clean_fixture(n=48000))
    write_wav(lib / 'slow80.wav', fx.decay_fixture(80.0, 0.030, n=48000))
    write_wav(lib / 'fast80.wav', fx.decay_fixture(80.0, 0.008, n=48000))
    win.library = scan_library([str(lib)], LibraryCache(str(lib / 'cache.json')))
    win._on_scan_done(win.library)
    print(f'extended: library {len(win.library)} IRs')
    assert len(win.library) == 4

    # legacy behavior through the subclass
    win.screen_panel.preset_list.setCurrentRow(0)
    win.screen_panel._emit_target()
    win._rank()
    n_ranked = win.library_panel.model.rowCount()
    assert 0 < n_ranked <= 25
    win._clear_rank()

    # workbench: A/B populate + the REAL worker pipeline (no audio needed)
    win.show_workbench()
    wb = win._workbench
    recs = win.library_panel.visible_records()
    wb.set_pair(recs[0], recs[1])

    # run the debounce + the actual PairAnalysisWorker synchronously
    wb._debounce.timeout.emit()
    results = {}
    from PySide6.QtCore import Qt
    wb._pair_worker.finished_ok.connect(
        lambda rid, res: results.__setitem__('pair_done', (rid, res)),
        Qt.DirectConnection)
    wb._pair_worker.failed.connect(
        lambda rid, msg: results.__setitem__('pair_failed', (rid, msg)),
        Qt.DirectConnection)
    wb._pair_worker.run()          # synchronous execution of the real job
    assert 'pair_done' in results, results.get('pair_failed')
    rid, result = results['pair_done']
    wb._pair_request_id = rid
    wb._on_pair_done(rid, result)
    print(f"workbench: {wb.status.text()}")
    assert wb.summary.table.rowCount() > 0
    assert wb.waveform._a.xData is not None and len(wb.waveform._a.xData) > 100

    # heavy tabs through the REAL AnalysisWorker jobs
    wb.tabs.setCurrentIndex(wb.tabs.indexOf(wb.tabs.widget(2)))   # CSD tab
    for key in ('csd_a', 'csd_b'):
        worker = wb._spec_workers.get(key)
        assert worker is not None, f'no worker for {key}'
        sink = {}
        worker.finished_ok.connect(lambda rid, res: sink.__setitem__('ok', res),
                                   Qt.DirectConnection)
        worker.failed.connect(lambda rid, m: sink.__setitem__('err', m),
                              Qt.DirectConnection)
        worker.run()
        assert 'ok' in sink, sink.get('err')
        wb._on_spec_done(key, worker.request_id, sink['ok'])
    assert wb.csd._decay_text.toPlainText(), 'band decay readout empty'

    for i in range(wb.tabs.count()):
        wb.tabs.setCurrentIndex(i)
        app.processEvents()
    print(f"workbench: renderer={'opengl' if wb.csd.using_opengl else '2d fallback'}")

    # response search end-to-end (tone shortlist -> fingerprints -> rank)
    from app.extensions.advanced_matching import rank_by_response, stage1_shortlist
    anchor = recs[0]
    short = stage1_shortlist(win.library, anchor.curve_db, max_tone_db=6.0,
                             top_k=10)
    assert short, 'anchor itself must pass its own tone constraint'
    fps = {r.path: wb.service.fingerprint(r) for r, _ in short}
    ranked = rank_by_response([r for r, _ in short], fps, wb.service,
                              anchor.curve_db,
                              weights={'tone': 1.0, 'd20': 1.0},
                              targets={'d20': 20.0}, policy='exclude',
                              max_tone_db=6.0)
    wb.search.show_results(ranked)
    eligible = sum(1 for c in ranked if not c.excluded)
    print(f"response search: {len(ranked)} candidates, {eligible} eligible")
    assert eligible >= 1

    # visual evidence
    png = os.path.join(tempfile.gettempdir(), 'bestir_extended.png')
    wb.resize(1250, 880)
    wb.grab().save(png)
    print(f'screenshot: {png}')
    wb.close()
    win.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
