"""Worker infrastructure for heavy extension analysis (WP-07).

Request IDs reject stale results; cooperative cancellation is checked between
analysis steps. All heavy work runs outside the Qt GUI thread.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.core.analysis import AnalysisResult


class AnalysisWorker(QThread):
    """Runs `job(service, context) -> result` for one request.

    `request_id` guards against out-of-order completion: the caller compares
    worker.request_id with the current one before touching plots.
    """
    finished_ok = Signal(int, object)     # request_id, result
    failed = Signal(int, str)             # request_id, message

    current_id = 0

    def __init__(self, job, parent=None):
        super().__init__(parent)
        AnalysisWorker.current_id += 1
        self.request_id = AnalysisWorker.current_id
        self._job = job
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        try:
            if self._cancelled:
                return
            result = self._job(self)
        except Exception as exc:   # surface, never crash the thread
            self.failed.emit(self.request_id, str(exc))
            return
        if self._cancelled:
            return
        self.finished_ok.emit(self.request_id, result)


class PairAnalysisWorker(QThread):
    """Computes A/B, pair comparison and blend prediction in one background job."""
    finished_ok = Signal(int, object)
    failed = Signal(int, str)

    current_id = 0

    def __init__(self, service, rec_a: AnalysisResult, rec_b: AnalysisResult,
                 parent=None):
        super().__init__(parent)
        PairAnalysisWorker.current_id += 1
        self.request_id = PairAnalysisWorker.current_id
        self._service = service
        self._a = rec_a
        self._b = rec_b
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from app.extensions.contracts import PairComparisonConfig
            from app.extensions.pair_compare import compare_pair, predict_blend
            if self._cancelled:
                return
            prep_a = self._service.prepared(self._a)
            prep_b = self._service.prepared(self._b)
            if self._cancelled:
                return
            cfg = PairComparisonConfig()
            pair = compare_pair(prep_a, prep_b, cfg)
            if self._cancelled:
                return
            blend = predict_blend(prep_a, prep_b, cfg, alignment='suggested')
            if self._cancelled:
                return
            env_a = self._service.envelope(self._a)
            if self._cancelled:
                return
            env_b = self._service.envelope(self._b)
            self.finished_ok.emit(self.request_id,
                                  {'pair': pair, 'blend': blend,
                                   'env_a': env_a, 'env_b': env_b})
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
