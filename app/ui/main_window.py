"""Main window: wires the library, plot, screening and inspector panels together."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QProgressBar, QSplitter, QVBoxLayout, QWidget)

from app.core.analysis import AnalysisResult
from app.core.audition import AuditionEngine
from app.core.cache import LibraryCache
from app.core.exporter import export_files
from app.core.matching import rank_records, score_curve
from app.core.tonematch import (DITone, curve_metrics, make_di_tone,
                                output_curve)
from .inspector_panel import InspectorPanel
from .library_panel import LibraryPanel
from .plot_panel import PlotPanel
from .screen_panel import ScreenPanel
from .workers import RecordWorker, ScanWorker, has_input_device


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('BestIR — IR screener')
        self.resize(1500, 900)

        self.settings = QSettings('BestIR', 'BestIR')
        self.cache = LibraryCache(os.path.join(
            os.environ.get('LOCALAPPDATA', '.'), 'BestIR', 'cache.json'))
        self.engine = AuditionEngine()
        self.library: list[AnalysisResult] = []
        self.ranked: list[AnalysisResult] | None = None
        self.top_paths: list[str] = []
        self._scan_worker: ScanWorker | None = None
        self._record_worker: RecordWorker | None = None
        self._di: DITone | None = None
        self._filtered: list[AnalysisResult] = []

        self.library_panel = LibraryPanel()
        self.plot = PlotPanel()
        self.screen_panel = ScreenPanel()
        self.inspector = InspectorPanel()

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.addWidget(self.plot, 1)
        center.addWidget(self.screen_panel, 0)
        center_w = QWidget()
        center_w.setLayout(center)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.library_panel)
        splitter.addWidget(center_w)
        splitter.addWidget(self.inspector)
        splitter.setSizes([640, 620, 340])
        self.setCentralWidget(splitter)

        self.status = QLabel('Ready.')
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.progress)

        # restore folders
        saved = self.settings.value('folders', []) or []
        if isinstance(saved, str):
            saved = [saved]
        for f in saved:
            if os.path.isdir(f):
                self.library_panel.folder_list.addItem(f)

        self._connect()
        self.inspector.set_di_available(False)
        if not has_input_device():
            self.screen_panel.record_btn.setEnabled(False)
            self.screen_panel.record_btn.setToolTip('No audio input device found')
        if self.library_panel.folders():
            self.start_scan()

    # ---- wiring ---------------------------------------------------------------
    def _connect(self):
        self.library_panel.folders_changed.connect(lambda _: self.start_scan())
        self.library_panel.rescan_requested.connect(lambda: self.start_scan(force=True))
        self.library_panel.filters_changed.connect(self._apply_filters)
        self.library_panel.selection_changed.connect(self._on_selection)

        self.screen_panel.rank_requested.connect(self._rank)
        self.screen_panel.clear_rank_requested.connect(self._clear_rank)
        self.screen_panel.target_changed.connect(self._on_target_changed)
        self.screen_panel.export_selected.connect(self._export_selected)
        self.screen_panel.export_topn.connect(self._export_topn)
        self.screen_panel.record_requested.connect(self._start_recording)
        self.screen_panel.record_cancel.connect(self._cancel_recording)
        self.screen_panel.load_di_requested.connect(self._load_di_file)
        self.screen_panel.di_cleared.connect(self._on_di_cleared)
        self.screen_panel.match_wav_requested.connect(self._load_match_wav)

        self.plot.curve_clicked.connect(self._on_plot_click)

        self.inspector.set_engine(self.engine)
        self.inspector.reference_requested.connect(self.screen_panel.set_reference)
        self.inspector.play_requested.connect(self._play_current)
        self.inspector.stop_requested.connect(self.engine.stop)
        self.inspector.ab_step.connect(self._ab_step)

        QShortcut(QKeySequence(Qt.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence('Ctrl+R'), self, self._rank)

    # ---- scanning -------------------------------------------------------------
    def start_scan(self, force: bool = False) -> None:
        folders = self.library_panel.folders()
        if not folders:
            return
        self.settings.setValue('folders', folders)
        if self._scan_worker and self._scan_worker.isRunning():
            return  # a scan is already running; it covers the same folders
        self.progress.setVisible(True)
        self.status.setText('Scanning…')
        self._scan_worker = ScanWorker(folders, self.cache, force=force)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_progress(self, done: int, total: int, path: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status.setText(f'Scanning {done}/{total}: '
                            f'{path.replace(chr(92), "/").rsplit("/", 1)[-1]}')

    def _on_scan_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.status.setText('Scan failed.')
        QMessageBox.warning(self, 'BestIR', f'Scan failed: {msg}')

    def _on_scan_done(self, results: list) -> None:
        self.progress.setVisible(False)
        self.library = results
        tags = sorted({t for r in results for t in r.tags})
        self.library_panel.set_available_tags(tags)
        self.status.setText(f'{len(results)} IRs loaded · '
                            f'cache: {len(self.cache)} entries')
        self._apply_filters()

    # ---- filtering / ranking -------------------------------------------------------
    def _apply_filters(self) -> None:
        filtered = self.library_panel.apply_filters(self.library)
        self._filtered = filtered
        self.library_panel.model.set_records(filtered)
        self.plot.set_records(filtered)
        self.ranked = None
        self.top_paths = []
        self.plot.set_top([])
        self.status.setText(f'{len(filtered)} of {len(self.library)} IRs shown')

    def _on_target_changed(self, target) -> None:
        self.plot.show_target(target)
        tm = self.screen_panel.is_tone_match_active()
        self.plot.show_di_curve(self._di.result.curve_db
                                if (tm and self._di) else None)
        self._update_output_preview()

    def _update_output_preview(self) -> None:
        """Show the chain output EQ (DI + selected IR) when tone matching."""
        if not (self.screen_panel.is_tone_match_active() and self._di):
            self.plot.show_output_curve(None)
            return
        sel = self.library_panel.selected_records()
        if not sel:
            self.plot.show_output_curve(None)
            self.screen_panel.set_output_summary('')
            return
        rec = sel[0]
        out = output_curve(self._di.result.curve_db, rec.curve_db)
        self.plot.show_output_curve(out)
        target = self.screen_panel._output_target_curve()
        lo, hi = self.screen_panel.score_range()
        parts = [f'{rec.path.replace(chr(92), "/").rsplit("/", 1)[-1]}']
        if target is not None:
            parts.append(f'output vs target: {score_curve(out, target, lo, hi):.2f} dB RMS')
        m = curve_metrics(out)
        parts.append(f'output tilt {m["tilt_db_oct"]:+.1f} dB/oct · '
                     f'flatness {m["flatness_db"]:.1f} dB')
        self.screen_panel.set_output_summary(' → '.join(parts))

    def _rank(self) -> None:
        target = self.screen_panel.current_target()
        if target is None:
            self.status.setText('Pick a preset / set sliders / draw a curve first.')
            return
        lo, hi = self.screen_panel.score_range()
        records = list(self._filtered)
        ranked = rank_records(records, target, lo, hi)
        self.ranked = ranked
        top_n = min(int(self.screen_panel.topn_spin.value()), len(ranked))
        self.top_paths = [r.path for r in ranked[:top_n]]
        # the table shows ONLY the matches (top N) — clear ranking to see all
        self.library_panel.model.set_records(ranked[:top_n], top_n=top_n)
        self.library_panel.table.sortByColumn(0, Qt.AscendingOrder)
        self.plot.set_top(self.top_paths)
        best = ranked[0]
        best_name = best.path.replace(chr(92), '/').rsplit('/', 1)[-1]
        self.status.setText(
            f'Ranked {len(ranked)} IRs — showing Top {top_n} only '
            f'(Clear ranking shows all) · best: {best_name} ({best.score:.2f} dB RMS)')

    def _clear_rank(self) -> None:
        self.ranked = None
        self.top_paths = []
        self.plot.set_top([])
        for r in self._filtered:
            r.score = None
        self.library_panel.model.set_records(self._filtered)
        self.status.setText('Ranking cleared.')

    # ---- tone match: DI capture ---------------------------------------------------
    def _start_recording(self, seconds: float) -> None:
        if self._record_worker and self._record_worker.isRunning():
            return
        self.screen_panel.begin_record()
        self._record_worker = RecordWorker(seconds)
        self._record_worker.progress.connect(
            lambda e, t=seconds: self.screen_panel.update_record_progress(e, t))
        self._record_worker.done.connect(self._on_record_done)
        self._record_worker.failed.connect(self._on_record_failed)
        self._record_worker.start()

    def _cancel_recording(self) -> None:
        if self._record_worker and self._record_worker.isRunning():
            self._record_worker.stop()

    def _on_record_done(self, data, sr: int) -> None:
        self.screen_panel.end_record()
        if len(data) < sr * 0.5:
            self.screen_panel.di_label.setText(
                'Recording too short or silent — check the input device.')
            return
        self._set_di(data, sr, 'Recorded DI')

    def _on_record_failed(self, msg: str) -> None:
        self.screen_panel.end_record()
        self.screen_panel.di_label.setText(f'Recording failed: {msg}')

    def _load_di_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load dry guitar DI', '', 'Audio (*.wav *.flac *.aiff)')
        if not path:
            return
        try:
            from app.core.audio_io import load_ir
            data, sr = load_ir(path)
        except Exception as exc:
            QMessageBox.warning(self, 'BestIR', f'Cannot read DI: {exc}')
            return
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        self._set_di(data, sr, name)

    def _set_di(self, data, sr: int, name: str) -> None:
        try:
            di = make_di_tone(data, sr, name)
        except ValueError as exc:
            self.screen_panel.di_label.setText(str(exc))
            return
        self._di = di
        peak_db = 20 * np.log10(float(np.max(np.abs(data))) + 1e-12)
        summary = (f'{len(data) / sr:.1f} s · peak {peak_db:.1f} dBFS'
                   f'{"  ⚠ CLIPPED" if peak_db > -0.1 else ""} · '
                   f'tilt {di.result.tilt_db_oct:+.1f} dB/oct · '
                   f'flatness {di.result.flatness_db:.1f} dB · '
                   f'{",".join(di.result.tags) or "no tag"}')
        self.screen_panel.set_di(di.result.curve_db, name, summary)
        self.plot.show_di_curve(di.result.curve_db)
        self.engine.set_di_signal(di.data, di.sr)
        self.inspector.set_di_available(True)
        self._update_output_preview()
        self.status.setText(f'DI tone ref set: {name}')

    def _on_di_cleared(self) -> None:
        self._di = None
        self.plot.show_di_curve(None)
        self.plot.show_output_curve(None)
        self.engine.clear_di_signal()
        self.inspector.set_di_available(False)

    def _load_match_wav(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load reference tone (its EQ becomes the output target)', '',
            'Audio (*.wav *.flac *.aiff)')
        if not path:
            self.screen_panel.cancel_match_wav()
            return
        try:
            from app.core.audio_io import load_ir
            from app.core.analysis import analyze_data
            data, sr = load_ir(path)
            res = analyze_data(data, sr, path=path)
        except Exception as exc:
            QMessageBox.warning(self, 'BestIR', f'Cannot read reference: {exc}')
            self.screen_panel.cancel_match_wav()
            return
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        self.screen_panel.set_custom_output_curve(res.curve_db, name)

    # ---- selection / inspector ------------------------------------------------------
    def _on_selection(self, records: list) -> None:
        paths = {r.path for r in records}
        self.plot.set_selected(paths)
        self.inspector.show_record(records[0] if records else None)
        self._update_output_preview()

    def _on_plot_click(self, path: str) -> None:
        for r in self.library_panel.model.records:
            if r.path == path:
                self.library_panel.select_record(r)
                return
        # after ranking the table holds only the top N; a click on a dimmed
        # curve still shows it in the inspector without touching the table
        for r in self._filtered:
            if r.path == path:
                self.plot.set_selected({path})
                self.inspector.show_record(r)
                return

    # ---- audition ---------------------------------------------------------------------
    def _play_current(self) -> None:
        rec = self.inspector._current
        if rec is None:
            return
        self._play_record(rec)

    def _play_record(self, rec: AnalysisResult) -> None:
        if not self.engine.available:
            self.inspector.status_label.setText('No audio output device found.')
            return
        try:
            self.engine.play(
                rec.path,
                self.inspector.source_combo.currentText(),
                level_match=self.inspector.level_match.isChecked(),
                loop=self.inspector.loop_check.isChecked(),
                volume=self.inspector.volume.value() / 100.0)
            name = rec.path.replace('\\', '/').rsplit('/', 1)[-1]
            self.inspector.status_label.setText(f'Playing {name}')
        except Exception as exc:
            self.inspector.status_label.setText(f'Playback error: {exc}')

    def _toggle_play(self) -> None:
        if self.engine.playing_path:
            self.engine.stop()
            self.inspector.status_label.setText('')
        else:
            self._play_current()

    def _ab_step(self, step: int) -> None:
        records = self.library_panel.visible_records()
        if not records:
            return
        current = self.inspector._current
        try:
            i = records.index(current)
        except ValueError:
            i = 0
        nxt = records[(i + step) % len(records)]
        self.library_panel.select_record(nxt)
        self._play_record(nxt)

    # ---- export -----------------------------------------------------------------------
    def _export(self, records: list[AnalysisResult]) -> None:
        if not records:
            self.status.setText('Nothing to export.')
            return
        dest = QFileDialog.getExistingDirectory(self, 'Export selected IRs to…')
        if not dest:
            return
        exported = export_files([r.path for r in records], dest)
        self.status.setText(f'Exported {len(exported)} file(s) to {dest}')

    def _export_selected(self) -> None:
        self._export(self.library_panel.selected_records())

    def _export_topn(self, n: int) -> None:
        if self.ranked is None:
            self.status.setText('Run a ranking first (Rank button).')
            return
        self._export(self.ranked[:n])

    def closeEvent(self, ev) -> None:  # noqa: N802
        self.engine.stop()
        if self._record_worker and self._record_worker.isRunning():
            self._record_worker.stop()
            self._record_worker.wait(2000)
        super().closeEvent(ev)
