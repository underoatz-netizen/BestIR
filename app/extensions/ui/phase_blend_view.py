"""Phase, group delay and blend prediction view (WP-07)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel,
                               QSlider, QTextEdit, QVBoxLayout, QWidget)

from app.ui.styles import SURFACE

_TICKS = [(100, '100'), (200, '200'), (500, '500'), (1000, '1k'), (2000, '2k'),
          (5000, '5k'), (10000, '10k')]


class PhaseBlendView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mag_a = self._make_plot('Magnitude (dB)')
        self._phase = self._make_plot('Phase after onset (rad, valid bins)')
        self._gd = self._make_plot('Group delay (ms)')
        self._blend = self._make_plot('Predicted blend magnitude (dB)')

        self.ratio_slider = QSlider(pg.QtCore.Qt.Horizontal)
        self.ratio_slider.setRange(0, 100)
        self.ratio_slider.setValue(50)
        self.ratio_label = QLabel('Blend: 50% B')

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(110)

        grid = QVBoxLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        for p in (self._mag_a, self._phase, self._gd, self._blend):
            grid.addWidget(p, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel('Blend ratio'))
        row.addWidget(self.ratio_slider, 1)
        row.addWidget(self.ratio_label)
        grid.addLayout(row)
        grid.addWidget(self.info)

        self._cache_a = None
        self._cache_b = None
        self._pair_result = None
        self._blend_result = None
        self.ratio_slider.valueChanged.connect(self._update_blend_plot)

    def _make_plot(self, label):
        p = pg.PlotWidget(background=SURFACE)
        p.setLabel('bottom', 'Frequency (Hz)')
        p.setLabel('left', label)
        p.showGrid(x=True, y=True, alpha=0.2)
        p.getAxis('bottom').setTicks(
            [[(float(np.log10(v)), lbl) for v, lbl in _TICKS]])
        return p

    @staticmethod
    def _lx(freqs):
        return np.log10(np.maximum(np.asarray(freqs, dtype=float), 1e-2))

    def show_pair(self, phase_a, phase_b, pair_result):
        self._phase.clear()
        self._gd.clear()
        self._cache_a, self._cache_b, self._pair_result = phase_a, phase_b, pair_result
        for ph, color in ((phase_a, '#5c9ce0'), (phase_b, '#e07a7a')):
            if ph is None or ph.phase_rad is None:
                continue
            lx = self._lx(ph.freqs)
            valid = ph.valid_mask
            self._phase.plot(x=lx[valid], y=ph.phase_rad[valid, 0],
                             pen=pg.mkPen(QColor(color), width=1))
            self._gd.plot(x=lx[valid], y=ph.group_delay_ms[valid, 0],
                          pen=pg.mkPen(QColor(color), width=1))
        self._update_info()

    def show_blend(self, pair_result, blend_result):
        self._pair_result = pair_result
        self._blend_result = blend_result
        self._update_blend_plot()
        self._update_info()

    def _update_blend_plot(self):
        blend = self._blend_result
        if blend is None or blend.magnitude_db is None:
            return
        pct = self.ratio_slider.value()
        idx = int(round(pct / 100.0 * (len(blend.ratios) - 1)))
        self.ratio_label.setText(f'Blend: {int(blend.ratios[idx] * 100)}% B')
        self._blend.clear()
        lx = self._lx(blend.freqs)
        self._blend.plot(x=lx, y=blend.magnitude_db[idx],
                         pen=pg.mkPen(QColor('#66d18a'), width=2))
        for f in blend.notch_freqs[:8]:
            line = pg.InfiniteLine(pos=float(np.log10(max(f, 1e-2))), angle=90,
                                   pen=pg.mkPen(QColor('#e07a7a'), width=1,
                                                style=pg.QtCore.Qt.DashLine))
            self._blend.addItem(line)

    def _update_info(self):
        pair, blend = self._pair_result, self._blend_result
        if pair is None:
            return
        lines = [f"Suggested alignment: delay {pair.delay_ms:+.2f} ms "
                 f"({pair.delay_samples:+.2f} samples), "
                 f"polarity {'same' if pair.polarity > 0 else 'INVERTED'}, "
                 f"confidence {pair.correlation_confidence:.2f}"]
        if blend is not None:
            if blend.worst_cancellation_db is not None:
                lines.append(
                    f'Worst cancellation: {blend.worst_cancellation_db:.1f} dB '
                    f'at {blend.worst_cancellation_freq:.0f} Hz '
                    f'(50/50 blend, suggested alignment)')
            if blend.rms_deviation_db is not None:
                lines.append(f'RMS deviation from power-sum expectation: '
                             f'{blend.rms_deviation_db:.2f} dB')
            if blend.phase_compat_score is not None:
                lines.append(f'Phase compatibility: '
                             f'{blend.phase_compat_score:.2f} / 1.00')
            if blend.sensitivity:
                s = ', '.join(f'{k}: {v:.1f} dB' for k, v in
                              blend.sensitivity.items() if v is not None)
                lines.append(f'Sensitivity to ±1 sample: {s}')
        self.info.setPlainText('\n'.join(lines))
