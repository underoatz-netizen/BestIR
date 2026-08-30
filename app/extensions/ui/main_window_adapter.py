"""ExtendedMainWindow: additive adapter over the legacy window (WP-07).

Subclasses — never edits — MainWindow. Adds a toolbar action that opens the
Compare A/B workbench and feeds library selection changes into it. Legacy
behavior, signals and layout are untouched.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar

from app.extensions.service import ResponseService
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

        # selection → workbench A/B
        self.library_panel.selection_changed.connect(self._push_selection)

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
            self._search_dialog.setWindowTitle('BestIR — Response Search')
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
        from app.extensions.advanced_matching import (rank_by_response,
                                                      stage1_shortlist)
        anchor = self.library_panel.selected_records()
        anchor = anchor[0] if anchor else self.library[0]
        target = np.asarray(anchor.curve_db, dtype=float)
        max_tone = request['constraints'].get('max_tone_db', 6.0)
        short = stage1_shortlist(self.library, target, max_tone_db=max_tone,
                                 top_k=40)
        records = [r for r, _ in short]
        service = self.response_service

        def job(worker):
            fps = {}
            for i, r in enumerate(records):
                if worker.cancelled:
                    break
                fps[r.path] = service.fingerprint(r)
            return rank_by_response(records, fps, service, target,
                                    weights=request['weights'],
                                    constraints=request['constraints'],
                                    policy=request['policy'],
                                    max_tone_db=max_tone)

        self.status.setText(f'Response search: analyzing {len(records)} '
                            'shortlisted IRs…')
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
