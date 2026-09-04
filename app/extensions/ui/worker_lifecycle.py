"""Small, GUI-owned lifecycle guard for extension QThread workers.

Cancellation is cooperative, so a worker may outlive the widget that started
it.  Keep such wrappers strongly referenced until their ``finished`` signal
arrives; otherwise Qt can destroy a running QThread during window teardown.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Slot


# Last-resort ownership for workers that do not finish during a bounded close.
# This deliberately lives outside QWidget ownership, whose destruction must
# never delete a running QThread wrapper.
_shutdown_retained_workers: list[object] = []
# Keep cleanup receivers alive independently of a closing widget.  A QThread's
# ``finished`` is emitted from its worker thread, so a lambda would otherwise
# remove from a UI-owned list on the wrong thread.
_retention_cleanups: list[QObject] = []


class _RetentionCleanup(QObject):
    def __init__(self, worker, retained: list[object]):
        super().__init__()
        self._worker = worker
        self._retained = retained

    @Slot()
    def release(self) -> None:
        if self._worker in self._retained:
            self._retained.remove(self._worker)
        if self in _retention_cleanups:
            _retention_cleanups.remove(self)


def _is_running(worker) -> bool:
    checker = getattr(worker, 'isRunning', None)
    return bool(checker()) if callable(checker) else False


def cancel(worker) -> None:
    callback = getattr(worker, 'cancel', None)
    if callable(callback):
        callback()


def retain_until_finished(worker, retained: list[object]) -> None:
    """Retain one worker locally, removing it when its thread finishes."""
    if worker is None or worker in retained:
        return
    retained.append(worker)
    finished = getattr(worker, 'finished', None)
    if finished is not None:
        cleanup = _RetentionCleanup(worker, retained)
        _retention_cleanups.append(cleanup)
        # A bound QObject slot gives Qt a receiver context and therefore a
        # queued GUI-thread delivery for real QThread signals.  It also keeps
        # the one-argument ``connect(slot)`` contract used by test doubles.
        finished.connect(cleanup.release)
        # The thread can finish in the small interval between the caller's
        # isRunning check and this connection.  Release immediately in that
        # case; a queued finished delivery, if any, is idempotent.
        if callable(getattr(worker, 'isRunning', None)) and not _is_running(worker):
            cleanup.release()


def cancel_and_retain(worker, retained: list[object]) -> None:
    cancel(worker)
    # A completed QThread is safe to release.  Unknown worker-shaped test
    # doubles are retained conservatively because they cannot prove that.
    if _is_running(worker) or not callable(getattr(worker, 'isRunning', None)):
        retain_until_finished(worker, retained)


def shutdown(workers, retained: list[object], timeout_ms: int = 200) -> None:
    """Cancel workers and wait briefly; retain any still-running wrappers.

    ``QThread.wait`` is intentionally bounded: jobs check cancellation between
    DSP stages, but a third-party decoder or I/O call must not freeze shutdown.
    """
    unique = []
    for worker in workers:
        if worker is not None and worker not in unique:
            unique.append(worker)
            cancel_and_retain(worker, retained)
    for worker in unique:
        if _is_running(worker):
            waiter = getattr(worker, 'wait', None)
            if callable(waiter):
                waiter(timeout_ms)
        if _is_running(worker):
            retain_until_finished(worker, _shutdown_retained_workers)
