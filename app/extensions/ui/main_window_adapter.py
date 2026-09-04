"""ExtendedMainWindow: additive adapter over the legacy window (WP-07).

Subclasses — never edits — MainWindow. Adds a toolbar action that opens the
Compare A/B workbench and feeds library selection changes into it. Legacy
behavior, signals and layout are untouched.
"""
from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSignalBlocker, Qt, Slot
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QPushButton

from app.extensions.service import ResponseService
from app.extensions.ui.styles_boro import (
    ACCENT_GOLD, ACCENT_GOLD_BG, BG_CANVAS, BORDER_CARD, COLOR_DIFF,
    COLOR_IR_A, COLOR_IR_A_BG, COLOR_IR_B, SURFACE_CARD, SURFACE_RAISED,
    TEXT_MUTED, FONT_FAMILY_MONO,
)
from app.ui.main_window import MainWindow
from .compare_workbench import CompareWorkbench
from .responsive_layout import ResponsiveLayoutAdapter
from .response_search_panel import ResponseSearchPanel
from .workers import AnalysisWorker
from .worker_lifecycle import cancel_and_retain, shutdown


class ExtendedMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.response_service = ResponseService()
        self._workbench = None
        self._search_panel = None
        self._search_dialog = None
        self._search_worker = None
        self._retired_workers = []
        self._closing = False
        self._workers_shutdown = False

        act_compare = QAction('Compare A/B', self)
        act_compare.triggered.connect(self.show_workbench)
        act_search = QAction('Response Search', self)
        act_search.triggered.connect(self.show_response_search)

        # selection -> workbench A/B
        self.library_panel.selection_changed.connect(self._push_selection)

        # U01 foundation: responsive action flow + inspector drawer + filter
        # wrap. Owns the extension toolbar (replaces the plain one).
        self._responsive = ResponsiveLayoutAdapter(
            self, actions=[act_compare, act_search])
        self._add_folder_removal()

        # Apply Boro visual overrides on top of inherited legacy widgets
        self._apply_boro_overrides()

    # ---- Boro Design System overrides ----------------------------------------
    def _apply_boro_overrides(self):
        """Patch hardcoded colors in legacy widgets to match Boro UI tokens.

        This runs after super().__init__() so all legacy panels are constructed.
        We override pyqtgraph backgrounds, pens, inline stylesheets, and the
        table model highlight color — all without editing app/ui/ source files.
        """
        self._patch_plot_panel()
        self._patch_inspector_panel()
        self._patch_screen_panel()
        self._patch_table_model()

    def _patch_plot_panel(self):
        """Instance-local Boro plot styling (B18: no module-global mutation).

        Legacy plot_panel._refresh_pens reads module-level pens; we do not
        overwrite those globals. This instance gets its own pen set applied
        to the existing items plus a bound _refresh_pens that keeps using it,
        so other PlotPanel instances (workbench plots, future windows) are
        unaffected.
        """
        # Canvas background: slate -> obsidian
        self.plot.setBackground(SURFACE_CARD)

        # Instance-local Boro pens
        self._boro_pens = {
            'curve': pg.mkPen(QColor(120, 130, 145, 50), width=1),
            'hover': pg.mkPen(QColor(ACCENT_GOLD), width=2),
            'sel': pg.mkPen(QColor(COLOR_IR_A), width=3),
            'top': pg.mkPen(QColor(66, 207, 0, 220), width=2),      # emerald
            'target': pg.mkPen(QColor(COLOR_DIFF), width=2,
                               style=Qt.DashLine),
            'di': pg.mkPen(QColor(254, 201, 3, 200), width=1.5),    # gold
            'output': pg.mkPen(QColor(COLOR_IR_A), width=2.5),      # cyan
        }

        # Existing items pick up the Boro pens immediately
        for item in self.plot._items.values():
            item.setPen(self._boro_pens['curve'])
        self.plot._target_item.setPen(self._boro_pens['target'])
        self.plot._di_item.setPen(self._boro_pens['di'])
        self.plot._output_item.setPen(self._boro_pens['output'])

        # Hover label text -> gold
        self.plot._hover_label.setColor(ACCENT_GOLD)

        # Instance-local refresh keeps Boro pens on every selection /
        # hover / top-N refresh without touching app/ui.plot_panel globals.
        import types
        boro_pens = self._boro_pens

        def boro_refresh(plot_self):
            for path, item in plot_self._items.items():
                if path in plot_self._selected:
                    item.setPen(boro_pens['sel'])
                    item.setZValue(30)
                elif path in plot_self._top:
                    item.setPen(boro_pens['top'])
                    item.setZValue(15)
                elif path == plot_self._hover_path:
                    item.setPen(boro_pens['hover'])
                    item.setZValue(20)
                else:
                    item.setPen(boro_pens['curve'])
                    item.setZValue(5)

        self.plot._refresh_pens = types.MethodType(boro_refresh, self.plot)

        # Grid alpha slightly lower for dark canvas
        pi = self.plot.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.15)

        # Axis label colors
        for axis_name in ('bottom', 'left'):
            ax = self.plot.getAxis(axis_name)
            ax.setTextPen(QColor(TEXT_MUTED))
            ax.setPen(QColor(BORDER_CARD))

    def _patch_inspector_panel(self):
        """Override inspector hardcoded colors to Boro palette."""
        # Mini waveform: slate -> obsidian card with cyan-tinted fill
        self.inspector.wave.setBackground(SURFACE_CARD)
        self.inspector.wave_item.setBrush(QColor(88, 188, 248, 40))  # cyan tint

        # Tag label: legacy green -> emerald
        self.inspector.tag_label.setStyleSheet(f'color: {COLOR_IR_B};')

        # Band bars: monkey-patch the set_values to use Boro colors
        original_set_values = self.inspector.bars.set_values.__func__

        def boro_set_values(bars_self, bands):
            from app.ui.styles import BORDER, SURFACE
            for name in bars_self._bars:
                v = float(np.clip(bands.get(name, 0.0), -12.0, 12.0))
                bar = bars_self._bars[name]
                bar.setValue(int(round((v - (-12.0)) / 24.0 * 100)))
                pos_color = COLOR_IR_B   # emerald for positive
                neg_color = COLOR_DIFF   # coral for negative
                chunk_color = pos_color if v >= 0 else neg_color
                bar.setStyleSheet(
                    f'QProgressBar {{ border: 1px solid {BORDER_CARD}; '
                    f'border-radius: 3px; background: {SURFACE_CARD}; }}'
                    f'QProgressBar::chunk {{ background: {chunk_color}; '
                    f'border-radius: 2px; }}')
                bars_self._values[name].setText(
                    f'{bands.get(name, 0.0):+.1f} dB')

        import types
        self.inspector.bars.set_values = types.MethodType(
            boro_set_values, self.inspector.bars)

        # Name label font weight
        self.inspector.name_label.setStyleSheet(
            f'font-weight: 600; font-size: 10pt;')

        # Metadata label in mono
        self.inspector.meta_label.setStyleSheet(
            f'color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; '
            f'font-size: 8pt;')

    def _patch_screen_panel(self):
        """Override screen panel hardcoded colors to Boro palette."""
        sp = self.screen_panel

        # Tone match hint text: legacy dim -> Boro muted
        sp.tm_hint.setStyleSheet(f'color: {TEXT_MUTED};')

        # Output label: legacy light cyan -> Boro electric cyan
        sp.output_label.setStyleSheet(f'color: {COLOR_IR_A};')

        # Make Rank buttons use Boro Gold primary style
        sp.rank_btn.setProperty('primary', True)
        sp.rank_btn.style().unpolish(sp.rank_btn)
        sp.rank_btn.style().polish(sp.rank_btn)

        sp.tm_rank_btn.setProperty('primary', True)
        sp.tm_rank_btn.style().unpolish(sp.tm_rank_btn)
        sp.tm_rank_btn.style().polish(sp.tm_rank_btn)

    def _patch_table_model(self):
        """Instance-local top-rank highlight (B18: no _TOP5_BG mutation).

        Wraps only this window's model.data so the legacy top-N BackgroundRole
        returns the Boro gold tint; app.ui.model._TOP5_BG stays untouched for
        every other window/model instance.
        """
        import types
        model = self.library_panel.model
        original_data = model.data.__func__
        gold_bg = QColor(ACCENT_GOLD_BG)

        def boro_data(model_self, index, role=Qt.DisplayRole):
            value = original_data(model_self, index, role)
            if role == Qt.BackgroundRole and value is not None:
                return gold_bg
            return value

        model.data = types.MethodType(boro_data, model)

    # ---- Extension-only folder management -----------------------------------
    def _add_folder_removal(self) -> None:
        """Add removal beside the inherited Add/Rescan controls.

        The legacy panel already owns folder persistence and scan signals; this
        adapter only removes selected roots and immediately hides their records.
        """
        self.remove_folder_btn = QPushButton('Remove Folder')
        self.remove_folder_btn.setToolTip('Remove selected folder(s) from this library')
        self.remove_folder_btn.setAccessibleName('Remove selected library folders')
        top_row = self.library_panel.layout().itemAt(0).layout()
        top_row.insertWidget(1, self.remove_folder_btn)
        self.remove_folder_btn.clicked.connect(self._remove_selected_folders)

    def _remove_selected_folders(self) -> None:
        folder_list = self.library_panel.folder_list
        selected_items = folder_list.selectedItems()
        if not selected_items:
            self.status.setText('Select one or more library folders to remove.')
            return
        removed_paths = {item.text() for item in selected_items}
        rows = sorted({index.row() for index in folder_list.selectedIndexes()},
                      reverse=True)
        with QSignalBlocker(folder_list.model()):
            for row in rows:
                folder_list.takeItem(row)
        # Filter in-memory library to exclude records from removed folders
        from pathlib import Path
        removed_roots = [Path(p).resolve() for p in removed_paths]
        kept = []
        for r in self.library:
            p = Path(r.path).resolve()
            is_removed = False
            for root in removed_roots:
                try:
                    p.relative_to(root)
                    is_removed = True
                    break
                except ValueError:
                    pass
            if not is_removed:
                kept.append(r)
        self.library = kept
        self._apply_filters()
        self.library_panel._emit_folders()
        if not self.library_panel.folders():
            self.settings.setValue('folders', [])
            self.status.setText('Library folders removed.')

    # ---- API used by the workbench -------------------------------------------
    def selected_library_records(self):
        return self.library_panel.selected_records()

    def library_records(self):
        return list(self.library)

    # ---- slots -----------------------------------------------------------------
    def _push_selection(self, records):
        if (not self._closing and not self._workers_shutdown and
                self._workbench is not None and self._workbench.isVisible()):
            self._workbench.set_selection(records)

    def show_workbench(self):
        if self._closing or self._workers_shutdown:
            return
        # A manually closed modeless workbench has shut down its workers.  Make
        # a new owner when reopening rather than reviving a closed one.
        if (self._workbench is None or
                getattr(self._workbench, '_workers_shutdown', False)):
            self._workbench = CompareWorkbench(self.response_service, parent=self)
            self._workbench.setWindowFlag(Qt.Window, True)
        self._workbench.show()
        self._workbench.raise_()
        self._workbench.set_selection(self.library_panel.selected_records())

    def show_response_search(self):
        if self._closing or self._workers_shutdown:
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout
        if self._search_dialog is None:
            self._search_dialog = QDialog(self)
            self._search_dialog.setWindowTitle('BestIR \u2014 Response Search')
            self._search_dialog.setModal(False)
            self._search_panel = ResponseSearchPanel(self._search_dialog)
            self._search_panel.rank_requested.connect(self._run_search)
            layout = QVBoxLayout(self._search_dialog)
            layout.addWidget(self._search_panel)
        self._search_dialog.show()
        self._search_dialog.raise_()

    def _run_search(self, request):
        if self._closing or self._workers_shutdown:
            return
        if not self.library:
            return
        from app.extensions.advanced_matching import response_search
        anchor = self.library_panel.selected_records()
        anchor = anchor[0] if anchor else self.library[0]
        target = np.asarray(anchor.curve_db, dtype=float)
        service = self.response_service

        def job(worker):
            # B16: one shared pipeline (stage1 shortlist -> fingerprint ->
            # rank). Heavy fingerprint DSP runs here, on the worker thread.
            return response_search(
                self.library, service, target,
                fingerprints_get=service.fingerprint,
                weights=request['weights'],
                constraints=request['constraints'],
                targets=request.get('targets'),  # B08
                policy=request['policy'],
                cancel=lambda: worker.cancelled)

        self.status.setText(f'Response search: analyzing shortlist by response...')
        if self._search_worker is not None:
            cancel_and_retain(self._search_worker, self._retired_workers)
        worker = AnalysisWorker(job)
        worker.finished_ok.connect(self._on_search_done)
        worker.failed.connect(self._on_search_failed)
        self._search_worker = worker
        worker.start()

    @Slot(int, object)
    def _on_search_done(self, request_id: int, ranked):
        worker = getattr(self, '_search_worker', None)
        if self._closing or self._workers_shutdown or not worker or worker.request_id != request_id:
            return
        self._search_panel.show_results(ranked)
        n_ok = sum(1 for c in ranked if not c.excluded)
        self.status.setText(f'Response search: {n_ok} eligible of '
                            f'{len(ranked)} shortlisted.')

    @Slot(int, str)
    def _on_search_failed(self, request_id: int, message: str):
        worker = getattr(self, '_search_worker', None)
        if self._closing or self._workers_shutdown or not worker or worker.request_id != request_id:
            return
        self.status.setText(f'Response search failed: {message}')

    def closeEvent(self, event):
        """Bounded, centralized shutdown for extension-owned workers/dialogs."""
        if self._workers_shutdown:
            super().closeEvent(event)
            return
        self._workers_shutdown = True
        self._closing = True
        if self._workbench is not None:
            self._workbench.shutdown_workers()
            self._workbench.close()
        if self._search_dialog is not None:
            self._search_dialog.close()
        # The inherited scanner is legacy-owned and may not support cooperative
        # cancellation.  Still retain/wait for its QThread wrapper so closing
        # this subclass cannot destroy it while it is running.
        workers = [self._search_worker, getattr(self, '_scan_worker', None),
                   *self._retired_workers]
        self._search_worker = None
        shutdown(workers, self._retired_workers)
        super().closeEvent(event)
