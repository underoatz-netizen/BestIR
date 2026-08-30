"""Compare A/B workbench (WP-07).

Two library rows populate A and B. Five tabs share the same source/config
identity; heavy computations run in workers with request IDs so stale results
never reach the plots, and results stay visible on failure.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from app.core.analysis import AnalysisResult
from app.extensions.service import ResponseService
from .csd_view import CsdView
from .phase_blend_view import PhaseBlendView
from .response_search_panel import ResponseSearchPanel
from .spectrogram_view import SpectrogramView
from .summary_panel import SummaryPanel
from .waveform_view import WaveformView
from .workers import AnalysisWorker, PairAnalysisWorker


def _short(path: str) -> str:
    return path.replace('\\', '/').rsplit('/', 1)[-1]


class CompareWorkbench(QDialog):
    """Modeless compare dialog owned by ExtendedMainWindow."""

    def __init__(self, service: ResponseService, parent=None):
        super().__init__(parent)
        self.setWindowTitle('BestIR — Compare A/B')
        self.setModal(False)
        self.resize(1250, 880)
        self.service = service

        self.rec_a: AnalysisResult | None = None
        self.rec_b: AnalysisResult | None = None
        self._pair_worker = None
        self._pair_request_id: int | None = None
        self._spec_workers = {}
        self._spec_cache = {}

        header = QHBoxLayout()
        self.label_a = QLabel('A: —')
        self.label_b = QLabel('B: —')
        self.btn_a = QPushButton('Set A ← selection')
        self.btn_b = QPushButton('Set B ← selection')
        header.addWidget(self.label_a, 1)
        header.addWidget(self.btn_a)
        header.addWidget(self.label_b, 1)
        header.addWidget(self.btn_b)

        self.summary = SummaryPanel()
        self.waveform = WaveformView()
        self.csd = CsdView()
        self.spectrogram = SpectrogramView()
        self.phase_blend = PhaseBlendView()
        self.search = ResponseSearchPanel(self)
        self.search.rank_requested.connect(self._run_response_search)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.summary, 'Summary')
        self.tabs.addTab(self.waveform, 'Waveform')
        self.tabs.addTab(self.csd, 'CSD')
        self.tabs.addTab(self.spectrogram, 'Spectrogram')
        self.tabs.addTab(self.phase_blend, 'Phase & Blend')
        self.tabs.addTab(self.search, 'Response Search')

        self.status = QLabel('Select two IRs in the library to populate A/B.')
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)

        self.btn_a.clicked.connect(self._set_a_from_selection)
        self.btn_b.clicked.connect(self._set_b_from_selection)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._compute_pair)

    # ---- A/B management -----------------------------------------------------
    def set_selection(self, records: list):
        """Called by ExtendedMainWindow on library selection changes."""
        if len(records) == 2:
            self.set_pair(records[0], records[1])
        elif len(records) == 1:
            if self.rec_a is None or self.rec_b is None or \
                    records[0].path not in (self.rec_a.path, self.rec_b.path):
                self._fill_slot(records[0])

    def _fill_slot(self, rec: AnalysisResult):
        if self.rec_a is None:
            self.set_a(rec)
        elif self.rec_b is None:
            self.set_b(rec)

    def set_pair(self, rec_a: AnalysisResult, rec_b: AnalysisResult):
        """Populate both slots at once (two selected library rows)."""
        self.rec_a = rec_a
        self.rec_b = rec_b
        self.label_a.setText(f'A: {_short(rec_a.path)}')
        self.label_b.setText(f'B: {_short(rec_b.path)}')
        self._invalidate()

    def set_a(self, rec: AnalysisResult):
        self.rec_a = rec
        self.label_a.setText(f'A: {_short(rec.path)}')
        self._invalidate()

    def set_b(self, rec: AnalysisResult):
        self.rec_b = rec
        self.label_b.setText(f'B: {_short(rec.path)}')
        self._invalidate()

    def _set_a_from_selection(self):
        rec = self._current_selection()
        if rec:
            self.set_a(rec)

    def _set_b_from_selection(self):
        rec = self._current_selection()
        if rec:
            self.set_b(rec)

    def _current_selection(self):
        parent = self.parent()
        getter = getattr(parent, 'selected_library_records', None)
        if getter:
            recs = getter()
            return recs[0] if recs else None
        return None

    def _invalidate(self):
        self._spec_cache.clear()
        if self.rec_a is None or self.rec_b is None:
            self.status.setText('Assign both A and B to compare.')
            return
        self.status.setText(f'Comparing {_short(self.rec_a.path)} ↔ '
                            f'{_short(self.rec_b.path)} — analyzing…')
        self._debounce.start()

    # ---- pair pipeline ---------------------------------------------------------
    def _compute_pair(self):
        if self.rec_a is None or self.rec_b is None:
            return
        if self._pair_worker and self._pair_worker.isRunning():
            self._pair_worker.cancel()
        a, b = self.rec_a, self.rec_b
        worker = PairAnalysisWorker(self.service, a, b)
        worker.finished_ok.connect(self._on_pair_done)
        worker.failed.connect(self._on_pair_failed)
        self._pair_worker = worker
        self._pair_request_id = worker.request_id
        worker.start()

    def _on_pair_done(self, request_id: int, result: dict):
        if self._pair_request_id != request_id:
            return   # stale result — ignore
        env_a, env_b = result['env_a'], result['env_b']
        self.waveform.show_envelopes(env_a, env_b)
        self.waveform.mark_onset_peak(env_a, '#5c9ce0', 'A')
        self.waveform.mark_onset_peak(env_b, '#e07a7a', 'B')
        self.summary.show_fingerprints(
            self._fingerprint(self.rec_a), self._fingerprint(self.rec_b),
            _short(self.rec_a.path), _short(self.rec_b.path))
        self.phase_blend.show_pair(self._phase(self.rec_a),
                                   self._phase(self.rec_b), result['pair'])
        self.phase_blend.show_blend(result['pair'], result['blend'])
        self.status.setText(f"Pair: delay {result['pair'].delay_ms:+.2f} ms, "
                            f"polarity {'same' if result['pair'].polarity > 0 else 'inverted'}")
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_pair_failed(self, request_id: int, msg: str):
        self.status.setText(f'Pair analysis failed: {msg}')

    def _fingerprint(self, rec):
        try:
            return self.service.fingerprint(rec)
        except Exception:
            return None

    def _phase(self, rec):
        try:
            return self.service.phase(rec)
        except Exception:
            return None

    # ---- tab-driven heavy views ---------------------------------------------------
    def _on_tab_changed(self, idx: int):
        if self.rec_a is None or self.rec_b is None:
            return
        title = self.tabs.tabText(idx)
        if title == 'CSD':
            self._ensure_spec('csd_a', self.rec_a)
            self._ensure_spec('csd_b', self.rec_b)
        elif title == 'Spectrogram':
            self._ensure_spec('spec_a', self.rec_a, spectrogram=True)
            self._ensure_spec('spec_b', self.rec_b, spectrogram=True)

    def _ensure_spec(self, cache_key: str, rec: AnalysisResult,
                     spectrogram: bool = False):
        if cache_key in self._spec_cache:
            self._apply_spec(cache_key, self._spec_cache[cache_key])
            return
        worker_key = cache_key
        old = self._spec_workers.get(worker_key)
        if old and old.isRunning():
            old.cancel()

        from app.extensions.csd import compute_csd
        from app.extensions.spectrogram import compute_spectrogram

        def job(worker):
            return (compute_spectrogram(self.service.prepared(rec))
                    if spectrogram else compute_csd(self.service.prepared(rec)))

        worker = AnalysisWorker(job)
        worker.finished_ok.connect(
            lambda rid, res, key=cache_key: self._on_spec_done(key, rid, res))
        worker.failed.connect(
            lambda rid, msg, key=cache_key: self._on_spec_failed(key, msg))
        self._spec_workers[worker_key] = worker
        worker.start()

    def _on_spec_done(self, cache_key: str, request_id: int, result):
        worker = self._spec_workers.get(cache_key)
        if not worker or worker.request_id != request_id:
            return   # stale
        self._spec_cache[cache_key] = result
        self._apply_spec(cache_key, result)

    def _on_spec_failed(self, cache_key: str, msg: str):
        self.status.setText(f'{cache_key} analysis failed: {msg}')

    def _apply_spec(self, cache_key: str, result):
        a_first = cache_key.endswith('_a')
        if cache_key.startswith('csd'):
            self._csd_results = getattr(self, '_csd_results', {})
            self._csd_results['a' if a_first else 'b'] = result
            ra = self._csd_results.get('a')
            rb = self._csd_results.get('b')
            if a_first:
                self.csd.show_csd(result, 'A')
            else:
                self.csd.show_csd(result, 'B')
        else:
            self._spec_results = getattr(self, '_spec_results', {})
            self._spec_results['a' if a_first else 'b'] = result
            if a_first:
                self._spec_a = result
            else:
                self._spec_b = result
            if getattr(self, '_spec_a', None) and getattr(self, '_spec_b', None):
                self.spectrogram.show_pair(self._spec_a, self._spec_b)
                self.spectrogram.show_metrics(
                    self._spec_a.metrics, self._spec_b.metrics)

    # ---- response search ------------------------------------------------------------
    def _run_response_search(self, request: dict):
        records = getattr(self.parent(), 'library_records', lambda: [])()
        if not records:
            self.status.setText('No library loaded.')
            return
        anchor = self.rec_a or self.rec_b or records[0]
        target = anchor.curve_db

        def job(worker):
            from app.extensions.advanced_matching import rank_by_response
            fps = {}
            for i, r in enumerate(records[:400]):
                if worker.cancelled:
                    break
                fps[r.path] = self.service.fingerprint(r)
            return rank_by_response(records, fps, self.service, target,
                                    weights=request['weights'],
                                    constraints=request['constraints'],
                                    policy=request['policy'])

        self.status.setText('Response search: fingerprinting shortlist…')
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
        self.search.show_results(ranked)
        self.status.setText(f'Response search: {len(ranked)} candidates ranked '
                            f'({sum(1 for c in ranked if not c.excluded)} eligible)')
