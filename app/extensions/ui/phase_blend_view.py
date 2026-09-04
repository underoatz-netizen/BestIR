"""Phase, group delay and blend prediction view (WP-07).

Enhanced with Boro UI design tokens, tactile blend slider, and comb-risk warning alerts.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QTextEdit, QVBoxLayout, QWidget)

from app.extensions.contracts import AnalysisStatus

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_DIFF, COLOR_IR_A,
                          COLOR_IR_B, FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                          SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .widgets.validity_chip import ValidityChip

_TICKS = [(100, '100'), (200, '200'), (500, '500'), (1000, '1k'), (2000, '2k'),
          (5000, '5k'), (10000, '10k')]


def _result_is_ok(result) -> bool:
    return result is not None and getattr(result, 'status', None) == AnalysisStatus.OK


def _blend_is_renderable(blend) -> bool:
    if not _result_is_ok(blend):
        return False
    if (getattr(blend, 'freqs', None) is None or
            getattr(blend, 'magnitude_db', None) is None or
            getattr(blend, 'ratios', None) is None):
        return False
    try:
        freqs = np.asarray(blend.freqs, dtype=float)
        magnitude = np.asarray(blend.magnitude_db, dtype=float)
        ratios = np.asarray(blend.ratios, dtype=float)
    except (TypeError, ValueError):
        return False
    return (freqs.ndim == 1 and freqs.size > 0 and
            ratios.ndim == 1 and ratios.size > 0 and
            magnitude.ndim == 2 and
            magnitude.shape == (ratios.size, freqs.size) and
            np.all(np.isfinite(freqs)) and np.all(freqs >= 0) and
            np.all(np.isfinite(magnitude)) and np.all(np.isfinite(ratios)))


def _unavailable_reason(pair, blend) -> str:
    for name, result in (('pair result', pair), ('blend result', blend)):
        if not _result_is_ok(result):
            reason = str(getattr(result, 'reason', '') or '').strip()
            if reason:
                return f'No data: {reason}'
            status = getattr(getattr(result, 'status', None), 'value',
                             getattr(result, 'status', None))
            return f'No data: {name} is {status or "unavailable"}'
    return 'No data: blend result is malformed'


def _risk_value(risk, name, default=None):
    if isinstance(risk, Mapping):
        return risk.get(name, default)
    return getattr(risk, name, default)


class PhaseBlendView(QWidget):
    export_aligned_b = Signal()
    export_blend = Signal()
    export_report = Signal()
    # U06: the user picked an alignment mode whose data is not present in the
    # current bundle — the owner (workbench) should recompute that alignment.
    alignment_requested = Signal(str)

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
        c_lay = QVBoxLayout(control_card)
        c_lay.setContentsMargins(10, 6, 10, 6)
        c_lay.setSpacing(6)

        ratio_row = QHBoxLayout()
        ratio_row.setSpacing(10)
        c_lay.addLayout(ratio_row)

        lbl = QLabel('Blend Ratio:')
        lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 9pt;")
        ratio_row.addWidget(lbl)

        a_tag = QLabel('100% A')
        a_tag.setStyleSheet(f"color: {COLOR_IR_A}; font-weight: 600; font-size: 8pt;")
        ratio_row.addWidget(a_tag)

        self.ratio_slider = QSlider(Qt.Horizontal)
        self.ratio_slider.setRange(0, 100)
        self.ratio_slider.setValue(50)
        ratio_row.addWidget(self.ratio_slider, 1)

        b_tag = QLabel('100% B')
        b_tag.setStyleSheet(f"color: {COLOR_IR_B}; font-weight: 600; font-size: 8pt;")
        ratio_row.addWidget(b_tag)

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
        ratio_row.addWidget(self.ratio_label)

        self.comb_chip = ValidityChip(text='Comb Risk: No data', state='invalid')
        ratio_row.addWidget(self.comb_chip)

        # U06: alignment mode selector — cached | raw | suggested. Selecting a
        # mode whose data is not in the current bundle emits alignment_requested
        # so the owner can recompute it (this view never runs DSP itself).
        align_row = QHBoxLayout()
        align_row.setSpacing(8)
        align_lbl = QLabel('Alignment:')
        align_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-weight: 600; font-size: 8.5pt;")
        align_row.addWidget(align_lbl)
        self.alignment_combo = QComboBox()
        for value, label in (('cached', 'Cached (current data)'),
                             ('raw', 'Raw (no alignment)'),
                             ('suggested', 'Suggested alignment')):
            self.alignment_combo.addItem(label, value)
        self.alignment_combo.setCurrentIndex(0)   # 'cached' before any signal
        self.alignment_combo.setStyleSheet(f"""
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
        """)
        self.alignment_combo.setToolTip(
            'Cached uses the blend data already in the bundle; Raw and '
            'Suggested request a recompute when their data is not cached yet.')
        align_row.addWidget(self.alignment_combo)
        align_row.addStretch(1)
        c_lay.addLayout(align_row)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(80)
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
        self.alignment_combo.currentIndexChanged.connect(
            self._on_alignment_changed)

    def _make_plot(self, label):
        p = pg.PlotWidget(background=SURFACE_CARD)
        p.setLabel('bottom', 'Frequency (Hz)', color=TEXT_MUTED)
        p.setLabel('left', label, color=TEXT_MUTED)
        p.showGrid(x=True, y=True, alpha=0.15)
        p.addLegend(offset=(10, 10))     # U06: each panel identifies its curves
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
        if not _result_is_ok(pair_result):
            self._blend_result = None
            self._show_blend_unavailable(pair_result, None)
            return
        for ph, color, name in ((phase_a, COLOR_IR_A, 'IR A'), (phase_b, COLOR_IR_B, 'IR B')):
            if ph is None or ph.phase_rad is None:
                continue
            lx = self._lx(ph.freqs)
            # per-channel validity (B11); the plot currently shows channel 0
            valid = ph.valid_mask[:, 0]
            self._phase.plot(x=lx[valid], y=ph.phase_rad[valid, 0],
                             pen=pg.mkPen(QColor(color), width=1.5), name=name)
            self._gd.plot(x=lx[valid], y=ph.group_delay_ms[valid, 0],
                          pen=pg.mkPen(QColor(color), width=1.5), name=name)
        self._update_info()

    def show_blend(self, pair_result, blend_result):
        self._pair_result = pair_result
        if not _result_is_ok(pair_result) or not _blend_is_renderable(blend_result):
            self._blend_result = None
            self._show_blend_unavailable(pair_result, blend_result)
            self._sync_alignment_combo()
            return
        self._blend_result = blend_result
        self._sync_alignment_combo()
        self._update_blend_plot()
        self._update_info()

    def current_ratio_b(self) -> float:
        blend = self._blend_result
        if blend is None or not len(blend.ratios):
            return 0.5
        pct = self.ratio_slider.value()
        idx = int(round(pct / 100.0 * (len(blend.ratios) - 1)))
        return float(blend.ratios[idx])

    def _active_risk(self, blend):
        risk_by_ratio = getattr(blend, 'risk_by_ratio', None)
        if not isinstance(risk_by_ratio, Mapping):
            return None
        return risk_by_ratio.get(self.current_ratio_b())

    def set_export_enabled(self, enabled: bool):
        for b in (self.btn_export_b, self.btn_export_blend, self.btn_export_report):
            b.setEnabled(enabled)

    # ---- U06 alignment selector ---------------------------------------------
    def _alignment_available(self, mode: str) -> bool:
        """True when the requested alignment mode is already present in the
        cached bundle — no recompute needed."""
        if mode == 'cached':
            return _blend_is_renderable(self._blend_result)
        return (_blend_is_renderable(self._blend_result) and
                getattr(self._blend_result, 'alignment', None) == mode)

    def _on_alignment_changed(self, *_):
        mode = self.alignment_combo.currentData()
        if self._alignment_available(mode):
            return
        self.alignment_requested.emit(mode)

    def _sync_alignment_combo(self):
        """Reflect the current bundle's alignment without emitting a request."""
        if _blend_is_renderable(self._blend_result):
            mode = getattr(self._blend_result, 'alignment', None)
            if mode not in ('raw', 'suggested'):
                mode = 'cached'
        else:
            mode = 'cached'
        self.alignment_combo.blockSignals(True)
        idx = self.alignment_combo.findData(mode)
        if idx >= 0:
            self.alignment_combo.setCurrentIndex(idx)
        self.alignment_combo.blockSignals(False)

    def _update_blend_plot(self):
        blend = self._blend_result
        self._blend.clear()
        if not _blend_is_renderable(blend):
            return
        n = len(blend.ratios)
        pct = self.ratio_slider.value()
        idx = int(round(pct / 100.0 * (n - 1)))
        # U06: snap the slider to the exact position of the nearest existing
        # ratio value so the displayed percentage always matches a real blend.
        snapped_pct = idx / (n - 1) * 100.0 if n > 1 else 0.0
        if abs(pct - snapped_pct) >= 1.0:
            self.ratio_slider.setValue(int(round(snapped_pct)))
            return      # the re-entrant valueChanged renders the snapped state
        ratio = float(blend.ratios[idx])
        pct_text = f'{round(ratio * 100)}% B'
        self.ratio_label.setText(f'Blend: {pct_text}')
        lx = self._lx(blend.freqs)
        self._blend.plot(x=lx, y=blend.magnitude_db[idx],
                         pen=pg.mkPen(QColor(ACCENT_GOLD), width=2.5),
                         name=f'Blend ({pct_text})')
        risk = self._active_risk(blend)
        for f in _risk_value(risk, 'notch_freqs', ())[:8]:
            line = pg.InfiniteLine(pos=float(np.log10(max(f, 1e-2))), angle=90,
                                   pen=pg.mkPen(QColor(COLOR_DIFF), width=1.5,
                                                style=Qt.DashLine))
            self._blend.addItem(line)
        self._update_info()

    def _show_blend_unavailable(self, pair, blend):
        reason = _unavailable_reason(pair, blend)
        self._blend.clear()
        self.ratio_label.setText('Blend: No data')
        self.comb_chip.set_state('invalid', 'Comb Risk: No data', reason)
        self.info.setPlainText(reason)
        self._sync_alignment_combo()

    def _update_info(self):
        pair, blend = self._pair_result, self._blend_result
        if not _result_is_ok(pair):
            self._show_blend_unavailable(pair, blend)
            return
        if blend is not None and not _blend_is_renderable(blend):
            self._show_blend_unavailable(pair, blend)
            return
        lines = [f"* Suggested Alignment: delay {pair.delay_ms:+.2f} ms "
                 f"({pair.delay_samples:+.2f} samples), "
                 f"Polarity: {'Normal (+)' if pair.polarity > 0 else 'INVERTED (-)'}, "
                 f"Correlation Confidence: {pair.correlation_confidence:.2f}"]
        if blend is not None:
            ratio = self.current_ratio_b()
            ratio_text = f'{int(ratio * 100)}% B blend'
            risk = self._active_risk(blend)
            try:
                loss = float(_risk_value(risk, 'worst_cancellation_db'))
            except (TypeError, ValueError):
                loss = None
            if loss is not None and np.isfinite(loss):
                freq = _risk_value(risk, 'worst_cancellation_freq')
                freq_text = f'at {float(freq):.0f} Hz ' if freq is not None else ''
                lines.append(
                    f'• Worst Notch Cancellation: {loss:.1f} dB {freq_text}'
                    f'({ratio_text})')
                if loss >= 6.0:
                    self.comb_chip.set_state('error', 'Comb Risk: High',
                                              f'Cancellation loss of {loss:.1f} dB '
                                              f'for {ratio_text}')
                elif loss >= 3.0:
                    self.comb_chip.set_state('warn', 'Comb Risk: Medium',
                                              f'Cancellation loss of {loss:.1f} dB '
                                              f'for {ratio_text}')
                else:
                    self.comb_chip.set_state('valid', 'Comb Risk: Safe',
                                              f'Minimal phase cancellation for {ratio_text}')
            else:
                self.comb_chip.set_state('invalid', 'Comb Risk: No data',
                                         f'No reliable cancellation data for {ratio_text}')
                lines.append(f'• Worst Notch Cancellation: No reliable data '
                             f'({ratio_text})')
            if blend.rms_deviation_db is not None:
                lines.append(f'• RMS Deviation from Power-Sum Expectation: '
                             f'{blend.rms_deviation_db:.2f} dB')
            if blend.phase_compat_score is not None:
                lines.append(f'• Phase Compatibility Score: '
                             f'{blend.phase_compat_score:.2f} / 1.00')
            sensitivity = _risk_value(risk, 'sensitivity', {})
            if isinstance(sensitivity, Mapping):
                s = ', '.join(f'{tag}: {value:.1f} dB' for tag in ('-1', '+1')
                              if (value := sensitivity.get(tag)) is not None)
                if s:
                    lines.append(f'• Sensitivity to +/-1 Sample Offset '
                                 f'({ratio_text}): {s}')
                else:
                    lines.append(f'• Sensitivity to +/-1 Sample Offset '
                                 f'({ratio_text}): No reliable data')
        self.info.setPlainText('\n'.join(lines))
