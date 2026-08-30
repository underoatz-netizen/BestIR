"""Phase, group delay and blend prediction view (WP-07).

Enhanced with Boro UI design tokens, tactile blend slider, and comb-risk warning alerts.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QTextEdit,
                               QVBoxLayout, QWidget)

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_DIFF, COLOR_IR_A,
                          COLOR_IR_B, FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                          SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .widgets.validity_chip import ValidityChip

_TICKS = [(100, '100'), (200, '200'), (500, '500'), (1000, '1k'), (2000, '2k'),
          (5000, '5k'), (10000, '10k')]


class PhaseBlendView(QWidget):
    export_aligned_b = Signal()
    export_blend = Signal()
    export_report = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mag_a = self._make_plot('Magnitude (dB)')
        self._phase = self._make_plot('Phase after onset (rad, valid bins)')
        self._gd = self._make_plot('Group delay (ms)')
        self._blend = self._make_plot('Predicted blend magnitude (dB)')

        # Blend control card
        control_card = QFrame()
        control_card.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        c_lay = QHBoxLayout(control_card)
        c_lay.setContentsMargins(10, 6, 10, 6)
        c_lay.setSpacing(10)

        lbl = QLabel('Blend Ratio:')
        lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 9pt;")
        c_lay.addWidget(lbl)

        a_tag = QLabel('100% A')
        a_tag.setStyleSheet(f"color: {COLOR_IR_A}; font-weight: 600; font-size: 8pt;")
        c_lay.addWidget(a_tag)

        self.ratio_slider = QSlider(Qt.Horizontal)
        self.ratio_slider.setRange(0, 100)
        self.ratio_slider.setValue(50)
        c_lay.addWidget(self.ratio_slider, 1)

        b_tag = QLabel('100% B')
        b_tag.setStyleSheet(f"color: {COLOR_IR_B}; font-weight: 600; font-size: 8pt;")
        c_lay.addWidget(b_tag)

        self.ratio_label = QLabel('Blend: 50% B')
        self.ratio_label.setStyleSheet(f"""
            color: {TEXT_MAIN};
            background-color: {SURFACE_RAISED};
            border: 1px solid {ACCENT_GOLD};
            border-radius: 6px;
            padding: 3px 8px;
            font-family: {FONT_FAMILY_MONO};
            font-weight: bold;
            font-size: 8.5pt;
        """)
        c_lay.addWidget(self.ratio_label)

        self.comb_chip = ValidityChip(text='Comb Risk: Low', state='valid')
        c_lay.addWidget(self.comb_chip)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(95)
        self.info.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
                padding: 6px 10px;
            }}
        """)

        export_box = QGroupBox('Export (non-destructive — sources stay untouched)')
        ex_lay = QHBoxLayout(export_box)
        self.btn_export_b = QPushButton('Export B (aligned)')
        self.btn_export_b.setToolTip('Write a copy of B with the suggested '
                                     'delay/polarity applied')
        self.btn_export_blend = QPushButton('Export Blend WAV')
        self.btn_export_blend.setToolTip('Write the A+B blend at the current '
                                         'ratio as a new IR')
        self.btn_export_report = QPushButton('Export Report (JSON)')
        self.btn_export_report.setToolTip('Write the measurement provenance: '
                                          'configs, units, warnings, signatures')
        for b in (self.btn_export_b, self.btn_export_blend, self.btn_export_report):
            ex_lay.addWidget(b)
        ex_lay.addStretch(1)

        grid = QVBoxLayout(self)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(6)

        # 2x2 or 4 rows layout for plots
        plots_grid = QGridLayout()
        plots_grid.setContentsMargins(0, 0, 0, 0)
        plots_grid.setSpacing(6)
        plots_grid.addWidget(self._phase, 0, 0)
        plots_grid.addWidget(self._gd, 0, 1)
        plots_grid.addWidget(self._blend, 1, 0, 1, 2)
        grid.addLayout(plots_grid, 1)

        grid.addWidget(control_card, 0)
        grid.addWidget(export_box, 0)
        grid.addWidget(self.info, 0)

        self.btn_export_b.clicked.connect(self.export_aligned_b.emit)
        self.btn_export_blend.clicked.connect(self.export_blend.emit)
        self.btn_export_report.clicked.connect(self.export_report.emit)

        self._cache_a = None
        self._cache_b = None
        self._pair_result = None
        self._blend_result = None
        self.ratio_slider.valueChanged.connect(self._update_blend_plot)

    def _make_plot(self, label):
        p = pg.PlotWidget(background=SURFACE_CARD)
        p.setLabel('bottom', 'Frequency (Hz)', color=TEXT_MUTED)
        p.setLabel('left', label, color=TEXT_MUTED)
        p.showGrid(x=True, y=True, alpha=0.15)
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
        for ph, color, name in ((phase_a, COLOR_IR_A, 'IR A'), (phase_b, COLOR_IR_B, 'IR B')):
            if ph is None or ph.phase_rad is None:
                continue
            lx = self._lx(ph.freqs)
            valid = ph.valid_mask
            self._phase.plot(x=lx[valid], y=ph.phase_rad[valid, 0],
                             pen=pg.mkPen(QColor(color), width=1.5), name=name)
            self._gd.plot(x=lx[valid], y=ph.group_delay_ms[valid, 0],
                          pen=pg.mkPen(QColor(color), width=1.5), name=name)
        self._update_info()

    def show_blend(self, pair_result, blend_result):
        self._pair_result = pair_result
        self._blend_result = blend_result
        self._update_blend_plot()
        self._update_info()

    def current_ratio_b(self) -> float:
        blend = self._blend_result
        if blend is None or not len(blend.ratios):
            return 0.5
        pct = self.ratio_slider.value()
        idx = int(round(pct / 100.0 * (len(blend.ratios) - 1)))
        return float(blend.ratios[idx])

    def set_export_enabled(self, enabled: bool):
        for b in (self.btn_export_b, self.btn_export_blend, self.btn_export_report):
            b.setEnabled(enabled)

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
                         pen=pg.mkPen(QColor(ACCENT_GOLD), width=2.5))
        for f in blend.notch_freqs[:8]:
            line = pg.InfiniteLine(pos=float(np.log10(max(f, 1e-2))), angle=90,
                                   pen=pg.mkPen(QColor(COLOR_DIFF), width=1.5,
                                                style=Qt.DashLine))
            self._blend.addItem(line)

    def _update_info(self):
        pair, blend = self._pair_result, self._blend_result
        if pair is None:
            return
        lines = [f"* Suggested Alignment: delay {pair.delay_ms:+.2f} ms "
                 f"({pair.delay_samples:+.2f} samples), "
                 f"Polarity: {'Normal (+)' if pair.polarity > 0 else 'INVERTED (-)'}, "
                 f"Correlation Confidence: {pair.correlation_confidence:.2f}"]
        if blend is not None:
            if blend.worst_cancellation_db is not None:
                lines.append(
                    f'• Worst Notch Cancellation: {blend.worst_cancellation_db:.1f} dB '
                    f'at {blend.worst_cancellation_freq:.0f} Hz (50/50 blend)')
                if blend.worst_cancellation_db < -6.0:
                    self.comb_chip.set_state('error', 'Comb Risk: High',
                                             f'Cancellation of {blend.worst_cancellation_db:.1f} dB at {blend.worst_cancellation_freq:.0f} Hz')
                elif blend.worst_cancellation_db < -3.0:
                    self.comb_chip.set_state('warn', 'Comb Risk: Medium',
                                             f'Cancellation of {blend.worst_cancellation_db:.1f} dB')
                else:
                    self.comb_chip.set_state('valid', 'Comb Risk: Safe', 'Minimal phase cancellation')
            if blend.rms_deviation_db is not None:
                lines.append(f'• RMS Deviation from Power-Sum Expectation: '
                             f'{blend.rms_deviation_db:.2f} dB')
            if blend.phase_compat_score is not None:
                lines.append(f'• Phase Compatibility Score: '
                             f'{blend.phase_compat_score:.2f} / 1.00')
            if blend.sensitivity:
                s = ', '.join(f'{k}: {v:.1f} dB' for k, v in
                              blend.sensitivity.items() if v is not None)
                lines.append(f'• Sensitivity to ±1 Sample Offset: {s}')
        self.info.setPlainText('\n'.join(lines))
