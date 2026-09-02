"""ExtendedMainWindow: additive adapter over the legacy window (WP-07).

Subclasses — never edits — MainWindow. Adds a toolbar action that opens the
Compare A/B workbench and feeds library selection changes into it. Legacy
behavior, signals and layout are untouched.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QToolBar

from app.extensions.service import ResponseService
from app.extensions.ui.styles_boro import (
    ACCENT_GOLD, ACCENT_GOLD_BG, BG_CANVAS, BORDER_CARD, COLOR_DIFF,
    COLOR_IR_A, COLOR_IR_A_BG, COLOR_IR_B, SURFACE_CARD, SURFACE_RAISED,
    TEXT_MUTED, FONT_FAMILY_MONO,
)
from app.ui.main_window import MainWindow
from .compare_workbench import CompareWorkbench
from .response_search_panel import ResponseSearchPanel
from .workers import AnalysisWorker


class ExtendedMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.response_service = ResponseService()
        self._workbench = None
        self._search_panel = None
        self._search_dialog = None

        toolbar = QToolBar('Response tools')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        act_compare = QAction('Compare A/B', self)
        act_compare.triggered.connect(self.show_workbench)
        toolbar.addAction(act_compare)
        act_search = QAction('Response Search', self)
        act_search.triggered.connect(self.show_response_search)
        toolbar.addAction(act_search)

        # selection -> workbench A/B
        self.library_panel.selection_changed.connect(self._push_selection)

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
        """Override plot background and curve pens to Boro palette."""
        import app.ui.plot_panel as pp

        # Canvas background: slate -> obsidian
        self.plot.setBackground(SURFACE_CARD)

        # Redefine pens with Boro tokens
        pp._CURVE_PEN = pg.mkPen(QColor(120, 130, 145, 50), width=1)
        pp._HOVER_PEN = pg.mkPen(QColor(ACCENT_GOLD), width=2)
        pp._SEL_PEN = pg.mkPen(QColor(COLOR_IR_A), width=3)
        pp._TOP_PEN = pg.mkPen(QColor(66, 207, 0, 220), width=2)  # emerald
        pp._TARGET_PEN = pg.mkPen(QColor(COLOR_DIFF), width=2,
                                   style=Qt.DashLine)
        pp._DI_PEN = pg.mkPen(QColor(254, 201, 3, 200), width=1.5)  # gold
        pp._OUTPUT_PEN = pg.mkPen(QColor(COLOR_IR_A), width=2.5)  # cyan

        # Hover label text -> gold
        self.plot._hover_label.setColor(ACCENT_GOLD)

        # Target curve pen
        self.plot._target_item.setPen(pp._TARGET_PEN)
        self.plot._di_item.setPen(pp._DI_PEN)
        self.plot._output_item.setPen(pp._OUTPUT_PEN)

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
        """Override table model top-rank highlight to Boro gold tint."""
        import app.ui.model as model_mod
        model_mod._TOP5_BG = QColor(ACCENT_GOLD_BG)

    # ---- API used by the workbench -------------------------------------------
    def selected_library_records(self):
        return self.library_panel.selected_records()

    def library_records(self):
        return list(self.library)

    # ---- slots -----------------------------------------------------------------
    def _push_selection(self, records):
        if self._workbench is not None and self._workbench.isVisible():
            self._workbench.set_selection(records)

    def show_workbench(self):
        if self._workbench is None:
            self._workbench = CompareWorkbench(self.response_service, parent=self)
            self._workbench.setWindowFlag(Qt.Window, True)
        self._workbench.show()
        self._workbench.raise_()
        self._workbench.set_selection(self.library_panel.selected_records())

    def show_response_search(self):
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
        worker = AnalysisWorker(job)
        worker.finished_ok.connect(self._on_search_done)
        worker.failed.connect(lambda rid, m: self.status.setText(
            f'Response search failed: {m}'))
        self._search_worker = worker
        worker.start()

    def _on_search_done(self, request_id: int, ranked):
        worker = getattr(self, '_search_worker', None)
        if not worker or worker.request_id != request_id:
            return
        self._search_panel.show_results(ranked)
        n_ok = sum(1 for c in ranked if not c.excluded)
        self.status.setText(f'Response search: {n_ok} eligible of '
                            f'{len(ranked)} shortlisted.')

