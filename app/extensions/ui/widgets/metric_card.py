"""MetricCard: Tactile Boro card displaying scalar acoustic metrics and deltas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_DIFF, COLOR_IR_A,
                           COLOR_IR_B, FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                           SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from ..metric_format import format_value, to_display_value
from .validity_chip import ValidityChip


class MetricCard(QFrame):
    """Boro-styled tactile card displaying metric title, large value, and delta.

    ``feature`` is the fingerprint feature key; raw cached values are converted
    to the declared display ``unit`` only at render time (B12, metric_format).
    """

    def __init__(self, title: str, unit: str = '', feature: str = '',
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 6px;
            }}
            MetricCard:hover {{
                border-color: #3e3e3e;
                background-color: {SURFACE_RAISED};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Title row
        top_row = QHBoxLayout()
        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 7.5pt; font-weight: 600; letter-spacing: 0.5px;")
        top_row.addWidget(self.title_lbl, 1)

        self.chip = ValidityChip(text='', state='valid')
        self.chip.setVisible(False)
        top_row.addWidget(self.chip, 0)
        layout.addLayout(top_row)

        # Value row (A vs B)
        val_row = QHBoxLayout()
        val_row.setSpacing(12)

        # IR A Value
        self.val_a_box = QVBoxLayout()
        self.val_a_lbl = QLabel('—')
        self.val_a_lbl.setStyleSheet(f"color: {COLOR_IR_A}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
        sub_a = QLabel('A')
        sub_a.setStyleSheet(f"color: {COLOR_IR_A}; font-size: 7pt; font-weight: 600;")
        self.val_a_box.addWidget(sub_a)
        self.val_a_box.addWidget(self.val_a_lbl)
        val_row.addLayout(self.val_a_box)

        # IR B Value
        self.val_b_box = QVBoxLayout()
        self.val_b_lbl = QLabel('—')
        self.val_b_lbl.setStyleSheet(f"color: {COLOR_IR_B}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
        sub_b = QLabel('B')
        sub_b.setStyleSheet(f"color: {COLOR_IR_B}; font-size: 7pt; font-weight: 600;")
        self.val_b_box.addWidget(sub_b)
        self.val_b_box.addWidget(self.val_b_lbl)
        val_row.addLayout(self.val_b_box)

        # Delta Value
        self.delta_box = QVBoxLayout()
        self.delta_lbl = QLabel('—')
        self.delta_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
        sub_d = QLabel('Δ (A−B)')
        sub_d.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 7pt; font-weight: 600;")
        self.delta_box.addWidget(sub_d)
        self.delta_box.addWidget(self.delta_lbl)
        val_row.addLayout(self.delta_box)

        val_row.addStretch(1)
        layout.addLayout(val_row)

        self._unit = unit
        self._feature = feature

    def set_values(self, val_a: float | None, val_b: float | None, note_a: str = '', note_b: str = '') -> None:
        # display-only unit conversion (raw cached values untouched)
        disp_a = to_display_value(self._feature, val_a, self._unit)
        disp_b = to_display_value(self._feature, val_b, self._unit)
        if disp_a is not None:
            self.val_a_lbl.setText(format_value(disp_a, self._unit))
            if note_a:
                self.val_a_lbl.setToolTip(f'A: {note_a}')
        else:
            self.val_a_lbl.setText('n/a')
            if note_a:
                self.val_a_lbl.setToolTip(f'A: {note_a}')

        if disp_b is not None:
            self.val_b_lbl.setText(format_value(disp_b, self._unit))
            if note_b:
                self.val_b_lbl.setToolTip(f'B: {note_b}')
        else:
            self.val_b_lbl.setText('n/a')
            if note_b:
                self.val_b_lbl.setToolTip(f'B: {note_b}')

        if disp_a is not None and disp_b is not None:
            delta = disp_a - disp_b
            self.delta_lbl.setText(
                format_value(delta, self._unit, signed=True, sig=3))
            if abs(delta) < 1e-6:
                self.delta_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
            else:
                color = COLOR_IR_A if delta > 0 else COLOR_IR_B
                self.delta_lbl.setStyleSheet(f"color: {color}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
        else:
            self.delta_lbl.setText('—')
            self.delta_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; font-size: 11pt; font-weight: 700;")
