"""Waveform/envelope comparison view (WP-07).

Enhanced with Boro UI color-coded envelope fills and high-contrast markers.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor

from .styles_boro import (ACCENT_GOLD, COLOR_IR_A, COLOR_IR_B, SURFACE_CARD,
                          TEXT_MAIN, TEXT_MUTED)


class WaveformView(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent, background=SURFACE_CARD)
        self.setLabel('bottom', 'Time after onset (ms)', color=TEXT_MUTED)
        self.setLabel('left', 'Normalized Envelope', color=TEXT_MUTED)
        self.showGrid(x=True, y=True, alpha=0.15)
        self.addLegend(offset=(10, 10))

        # IR A (Cyan) with semi-transparent fill
        self._a = self.plot(pen=pg.mkPen(QColor(COLOR_IR_A), width=2),
                            name='IR A',
                            brush=QBrush(QColor(88, 188, 248, 25)),
                            fillLevel=0)
        # IR B (Emerald) with semi-transparent fill
        self._b = self.plot(pen=pg.mkPen(QColor(COLOR_IR_B), width=2),
                            name='IR B',
                            brush=QBrush(QColor(66, 207, 0, 25)),
                            fillLevel=0)
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
                               pen=pg.mkPen(QColor(color), width=1.5,
                                            style=Qt.DashLine),
                               label=label,
                               labelOpts={'color': QColor(color), 'position': 0.85})
        self.addItem(line)
        self._lines.append(line)

    def _clear_markers(self):
        for line in self._lines:
            self.removeItem(line)
        self._lines = []

    def mark_onset_peak(self, env, color, prefix):
        if env is None:
            return
        if env.hilbert_env is not None and len(env.hilbert_env):
            i = int(np.argmax(env.hilbert_env))
            t_peak = float(env.time_ms[i]) if env.time_ms is not None else 0.0
            self.add_marker(t_peak, color, f'{prefix} peak ({t_peak:.2f} ms)')
