"""Offscreen GUI smoke test: full workflow without a display or audio.

Run: QT_QPA_PLATFORM=offscreen python tests/gui_smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

import app.ui.main_window as mw_module
from app.core.cache import LibraryCache
from app.core.scanner import scan_library

IR_ROOT = r'E:\Projects\BestIR\IR'


def main() -> int:
    app = QApplication([])
    win = mw_module.MainWindow()

    # deterministic scan of the real pack (synchronous, not via worker)
    cache = LibraryCache(os.path.join(tempfile.gettempdir(), 'bestir_gui_cache.json'))
    win.library = scan_library([IR_ROOT], cache)
    print(f'library: {len(win.library)} files')
    assert len(win.library) > 300

    tags = sorted({t for r in win.library for r_tags in [r.tags] for t in r_tags})
    win.library_panel.set_available_tags(tags)
    win._on_scan_done(win.library)
    assert win.library_panel.model.rowCount() > 300, 'table should hold all IRs'

    # filters: only 48k (combo index 2 = '48000')
    win.library_panel.sr_combo.setCurrentIndex(2)
    shown48 = win.library_panel.model.rowCount()
    print(f'48 kHz filter -> {shown48} rows')
    assert 0 < shown48 < len(win.library)
    win.library_panel.sr_combo.setCurrentIndex(0)

    # preset ranking — table shows ONLY the top-N matches
    win.screen_panel.preset_list.setCurrentRow(0)  # Flat
    win.screen_panel._emit_target()
    win._rank()
    first = win.library_panel.model.records[0]
    assert first.score is not None
    assert win.library_panel.model.rowCount() == 25, 'table should show top-25 only'
    print(f"Flat ranking best: {Path(first.path).name} ({first.score:.2f} dB), "
          f"table rows: {win.library_panel.model.rowCount()}")
    win._clear_rank()
    assert win.library_panel.model.rowCount() == len(win.library), \
        'clear ranking must restore the full list'

    # scooped preset ranking should differ from flat ranking
    win.screen_panel.preset_list.setCurrentRow(3)  # Scooped
    win.screen_panel._emit_target()
    win._rank()
    scooped_best = win.library_panel.model.records[0]
    print(f"Scooped ranking best: {Path(scooped_best.path).name}")
    assert scooped_best.score <= first.score + 5.0
    win._clear_rank()

    # band sliders ranking
    win.screen_panel.tabs.setCurrentIndex(1)
    win.screen_panel.band_sliders['High'].setValue(40)  # +4 dB high
    win._rank()
    bright_best = win.library_panel.model.records[0]
    print(f"+High ranking best: {Path(bright_best.path).name}")
    win._clear_rank()

    # reference mode
    win.screen_panel.set_reference(win.library[0])
    assert win.screen_panel.current_target() is not None
    win.screen_panel.clear_reference()

    # selection -> inspector
    win.library_panel.table.selectRow(5)
    rec = win.library_panel.selected_records()
    assert len(rec) == 1
    win.inspector.show_record(rec[0])
    assert rec[0].path.rsplit('/', 1)[-1].split(chr(92))[-1] in win.inspector.name_label.text()

    # export the currently selected row to a temp dir
    out_dir = tempfile.mkdtemp(prefix='bestir_export_')
    from app.core.exporter import export_files
    exported = export_files([r.path for r in rec], out_dir)
    assert len(exported) == 1 and os.path.exists(exported[0])
    print(f'export OK: {exported[0]}')

    # ---- tone match workflow (DI via synth file, no mic needed) --------------
    from tests.synth import synth_ir
    di_sig = synth_ir(sr=48000, n=48000,
                      anchors_db=[0, -1, -2, -4, -6, -8, -10, -14], seed=5)
    win._set_di(di_sig, 48000, 'synth DI')
    assert win._di is not None and win.inspector.source_combo.findText('Recorded DI') >= 0

    win.screen_panel.tabs.setCurrentIndex(win.screen_panel.TONE_MATCH_IDX)
    assert win.screen_panel.current_target() is not None  # needed-IR curve
    win.screen_panel.tm_rank_btn.click()  # the in-tab Find Matching IRs button
    tm_best = win.library_panel.model.records[0]
    assert win.library_panel.model.rowCount() == 25
    print(f'Tone-match (balanced out) best: {Path(tm_best.path).name} '
          f'({tm_best.score:.2f} dB)')

    # a wanted output tone changes the needed IR and the ranking
    idx = win.screen_panel.out_combo.findText('Bright')
    win.screen_panel.out_combo.setCurrentIndex(idx)
    win._rank()
    tm_bright = win.library_panel.model.records[0]
    print(f'Tone-match (bright out) best: {Path(tm_bright.path).name}')
    win._clear_rank()

    # selecting an IR on the tone match tab shows the output EQ summary
    win.library_panel.table.selectRow(3)
    app.processEvents()
    assert 'output tilt' in win.screen_panel.output_label.text(), \
        win.screen_panel.output_label.text()
    print(f"output preview: {win.screen_panel.output_label.text()}")

    # audition engine serves the recorded DI as a source
    sig = win.engine.test_signal('Recorded DI', win.engine.device_sr)
    assert len(sig) > 0
    win.screen_panel.clear_di()
    assert win._di is None
    assert win.inspector.source_combo.findText('Recorded DI') < 0

    # A/B navigation must not actually play (no device access here)
    win.engine.available = False
    win.engine._sd = None
    win._ab_step(1)

    # render a screenshot for visual inspection
    win.resize(1600, 950)
    win.show()
    app.processEvents()
    png = os.path.join(tempfile.gettempdir(), 'bestir_gui.png')
    win.grab().save(png)
    print(f'screenshot: {png}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
