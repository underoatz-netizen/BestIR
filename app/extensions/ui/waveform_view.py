"""Waveform/envelope comparison view (WP-07)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor

from app.ui.styles import SURFACE


class WaveformView(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent, background=SURFACE)
        self.setLabel('bottom', 'Time after onset (ms)')
        self.setLabel('left', 'Normalized envelope')
        self.showGrid(x=True, y=True, alpha=0.2)
        self._a = self.plot(pen=pg.mkPen(QColor('#5c9ce0'), width=1.5), name='A')
        self._b = self.plot(pen=pg.mkPen(QColor('#e07a7a'), width=1.5), name='B')
        self._lines = []

    def show_envelopes(self, env_a=None, env_b=None):
        for item, env in ((self._a, env_a), (self._b, env_b)):
            if env is None or env.time_ms is None:
                item.setData([], [])
                continue
            t = np.asarray(env.time_ms, dtype=float)
            y = np.asarray(env.hilbert_env, dtype=float)
            item.setData(t, y)
        self._clear_markers()

    def add_marker(self, x_ms: float, color: str, label: str):
        line = pg.InfiniteLine(pos=x_ms, angle=90,
                               pen=pg.mkPen(QColor(color), width=1,
                                            style=pg.QtCore.Qt.DashLine),
                               label=label)
        self.addItem(line)
        self._lines.append(line)

    def _clear_markers(self):
        for line in self._lines:
            self.removeItem(line)
        self._lines = []

    def mark_onset_peak(self, env, color, prefix):
        if env is None:
            return
        # peak marker on the envelope grid
        if env.hilbert_env is not None and len(env.hilbert_env):
            i = int(np.argmax(env.hilbert_env))
            t_peak = float(env.time_ms[i]) if env.time_ms is not None else 0.0
            self.add_marker(t_peak, color, f'{prefix} peak')
