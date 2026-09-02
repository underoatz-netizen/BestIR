"""Waveform/envelope comparison view (WP-07).

Enhanced with Boro UI color-coded envelope fills, high-contrast markers, a
selectable envelope estimate (Hilbert / RMS / peak-hold) and Full/Attack/Tail
time zoom (U05).

The pair-analysis bundle carries envelope/energy estimates only — there is no
raw signed sample buffer — so the raw waveform is intentionally not plotted;
the control row states that reason explicitly.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_IR_A, COLOR_IR_B,
                          FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY, SURFACE_CARD,
                          SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)

# U05: the bundle has no sample buffer, so a raw signed waveform trace cannot
# be drawn — the UI documents this reason instead of faking a signal.
RAW_OMITTED_REASON = ('Raw signed waveform not shown: the analysis bundle '
                      'carries envelope/energy estimates only (no sample '
                      'buffer).')

_ENVELOPE_MODES = (('hilbert', 'Hilbert envelope'),
                   ('rms', 'RMS envelope'),
                   ('peak', 'Peak-hold envelope'))

_ZOOM_MODES = (('full', 'Full'), ('attack', 'Attack'), ('tail', 'Tail'))

# U05: attack/tail split point for IR-style transients (first N ms after onset
# is the attack band, everything after is the decay tail).
_ATTACK_MS = 10.0

_Y_LABELS = {'hilbert': 'Normalized Hilbert Envelope',
             'rms': 'Normalized RMS Envelope',
             'peak': 'Normalized Peak-Hold Envelope'}

_COMBO_QSS = f"""
    QComboBox {{
        background-color: {SURFACE_RAISED};
        border: 1px solid {BORDER_CARD};
        border-radius: 6px;
        padding: 3px 8px;
        color: {TEXT_MAIN};
        font-family: {FONT_FAMILY_PRIMARY};
        font-size: 8.5pt;
    }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox QAbstractItemView {{
        background-color: {SURFACE_RAISED};
        color: {TEXT_MAIN};
        border: 1px solid {BORDER_CARD};
        selection-background-color: {ACCENT_GOLD};
        selection-color: #000000;
    }}
"""


class WaveformView(QWidget):
    """Envelope comparison panel: A/B curves, marker overlays, an envelope-mode
    selector and Full/Attack/Tail zoom.

    The public plotting API (``show_envelopes`` / ``add_marker`` /
    ``mark_onset_peak``) and the ``_a`` / ``_b`` curve items are retained, so
    existing callers keep working unchanged.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # U05: control row — envelope estimate, time zoom, raw-data reason.
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        mode_lbl = QLabel('Envelope:')
        mode_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8.5pt;")
        ctrl.addWidget(mode_lbl)
        self.envelope_combo = QComboBox()
        for value, label in _ENVELOPE_MODES:
            self.envelope_combo.addItem(label, value)
        self.envelope_combo.setCurrentIndex(0)   # 'hilbert' before any signal
        self.envelope_combo.setStyleSheet(_COMBO_QSS)
        self.envelope_combo.setToolTip(
            'Envelope estimate to display: analytic Hilbert magnitude, '
            'short-window RMS energy, or monotone peak-hold.')
        ctrl.addWidget(self.envelope_combo)

        zoom_lbl = QLabel('Zoom:')
        zoom_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8.5pt;")
        ctrl.addWidget(zoom_lbl)
        self.zoom_combo = QComboBox()
        for value, label in _ZOOM_MODES:
            self.zoom_combo.addItem(label, value)
        self.zoom_combo.setCurrentIndex(0)       # 'full' before any signal
        self.zoom_combo.setStyleSheet(_COMBO_QSS)
        self.zoom_combo.setToolTip(
            f'Time zoom: Full range, Attack (first {_ATTACK_MS:.0f} ms after '
            f'onset), or Tail (decay after the attack band).')
        ctrl.addWidget(self.zoom_combo)

        ctrl.addSpacing(10)
        self.raw_reason_label = QLabel(RAW_OMITTED_REASON)
        self.raw_reason_label.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-family: {FONT_FAMILY_MONO};
            font-size: 7.5pt;
        """)
        self.raw_reason_label.setWordWrap(True)
        ctrl.addWidget(self.raw_reason_label, 1)
        lay.addLayout(ctrl)

        # embedded plot — keeps the A/B curve items and marker overlays
        self.plot = pg.PlotWidget(background=SURFACE_CARD)
        self.plot.setLabel('bottom', 'Time after onset (ms)', color=TEXT_MUTED)
        self.plot.setLabel('left', _Y_LABELS['hilbert'], color=TEXT_MUTED)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.addLegend(offset=(10, 10))

        # IR A (Cyan) with semi-transparent fill
        self._a = self.plot.plot(pen=pg.mkPen(QColor(COLOR_IR_A), width=2),
                                 name='IR A',
                                 brush=QBrush(QColor(88, 188, 248, 25)),
                                 fillLevel=0)
        # IR B (Emerald) with semi-transparent fill
        self._b = self.plot.plot(pen=pg.mkPen(QColor(COLOR_IR_B), width=2),
                                 name='IR B',
                                 brush=QBrush(QColor(66, 207, 0, 25)),
                                 fillLevel=0)
        self._lines = []
        self._env_a = None
        self._env_b = None

        lay.addWidget(self.plot, 1)

        self.envelope_combo.currentIndexChanged.connect(self._render)
        self.zoom_combo.currentIndexChanged.connect(self._apply_zoom)

    # ---- public plotting API (retained) ------------------------------------
    def show_envelopes(self, env_a=None, env_b=None):
        self._env_a, self._env_b = env_a, env_b
        self._render()

    def add_marker(self, x_ms: float, color: str, label: str):
        line = pg.InfiniteLine(pos=x_ms, angle=90,
                               pen=pg.mkPen(QColor(color), width=1.5,
                                            style=Qt.DashLine),
                               label=label,
                               labelOpts={'color': QColor(color), 'position': 0.85})
        self.plot.addItem(line)
        self._lines.append(line)

    def mark_onset_peak(self, env, color, prefix):
        if env is None:
            return
        if env.hilbert_env is not None and len(env.hilbert_env):
            i = int(np.argmax(env.hilbert_env))
            t_peak = float(env.time_ms[i]) if env.time_ms is not None else 0.0
            self.add_marker(t_peak, color, f'{prefix} peak ({t_peak:.2f} ms)')

    def _clear_markers(self):
        for line in self._lines:
            self.plot.removeItem(line)
        self._lines = []

    # ---- U05 selectors ------------------------------------------------------
    def set_envelope_mode(self, mode: str):
        """Switch the plotted envelope estimate: 'hilbert' | 'rms' | 'peak'."""
        idx = self.envelope_combo.findData(mode)
        if idx >= 0:
            self.envelope_combo.setCurrentIndex(idx)

    def set_zoom_mode(self, mode: str):
        """Switch the time zoom: 'full' | 'attack' | 'tail'."""
        idx = self.zoom_combo.findData(mode)
        if idx >= 0:
            self.zoom_combo.setCurrentIndex(idx)

    def envelope_mode(self) -> str:
        return self.envelope_combo.currentData()

    def zoom_mode(self) -> str:
        return self.zoom_combo.currentData()

    # ---- rendering ----------------------------------------------------------
    def _envelope_array(self, env):
        if env is None:
            return None
        mode = self.envelope_mode()
        if mode == 'rms':
            return env.rms_env
        if mode == 'peak':
            return env.peak_hold_env
        return env.hilbert_env

    def _render(self, *_):
        self.plot.setLabel('left',
                           _Y_LABELS.get(self.envelope_mode(),
                                         _Y_LABELS['hilbert']),
                           color=TEXT_MUTED)
        for item, env in ((self._a, self._env_a), (self._b, self._env_b)):
            if env is None or env.time_ms is None:
                item.setData([], [])
                continue
            y = self._envelope_array(env)
            if y is None:
                item.setData([], [])
                continue
            t = np.asarray(env.time_ms, dtype=float)
            item.setData(t, np.asarray(y, dtype=float))
        self._clear_markers()
        self._apply_zoom()

    def _full_x_range(self):
        for env in (self._env_a, self._env_b):
            if env is not None and env.time_ms is not None and len(env.time_ms):
                t = np.asarray(env.time_ms, dtype=float)
                return float(t[0]), float(t[-1])
        return None

    def _apply_zoom(self, *_):
        rng = self._full_x_range()
        if rng is None:
            return
        t0, t1 = rng
        if t1 <= t0:
            t1 = t0 + 1.0
        mode = self.zoom_mode()
        attack_end = min(t0 + _ATTACK_MS, t1)
        if mode == 'attack':
            x0, x1 = t0, attack_end
        elif mode == 'tail':
            if attack_end >= t1 - 1e-9:      # nothing beyond the attack band
                x0, x1 = t0, t1
            else:
                x0, x1 = attack_end, t1
        else:
            x0, x1 = t0, t1
        self.plot.setXRange(x0, x1, padding=0)