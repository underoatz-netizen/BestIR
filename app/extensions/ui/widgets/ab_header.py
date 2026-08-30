"""ABHeaderDeck: Dual-deck header card for IR A and IR B with Boro aesthetic."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from app.core.analysis import AnalysisResult
from ..styles_boro import (ACCENT_GOLD, BORDER_CARD, BORDER_FOCUS,
                           COLOR_IR_A, COLOR_IR_A_BG, COLOR_IR_A_BORDER,
                           COLOR_IR_B, COLOR_IR_B_BG, COLOR_IR_B_BORDER,
                           FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                           SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .validity_chip import ValidityChip


def _short_name(path: str) -> str:
    if not path:
        return '—'
    return Path(path).name


class IRDeckCard(QFrame):
    """Single IR deck card (A or B) with accent stripe."""

    set_requested = Signal()

    def __init__(self, slot: str = 'A', color: str = COLOR_IR_A, parent: QWidget | None = None):
        super().__init__(parent)
        self._slot = slot
        self._color = color
        self.setFrameShape(QFrame.StyledPanel)
        
        bg_col = COLOR_IR_A_BG if slot == 'A' else COLOR_IR_B_BG
        bd_col = COLOR_IR_A_BORDER if slot == 'A' else COLOR_IR_B_BORDER

        self.setStyleSheet(f"""
            IRDeckCard {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-left: 4px solid {color};
                border-radius: 8px;
                padding: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Slot badge
        slot_lbl = QLabel(slot)
        slot_lbl.setAlignment(Qt.AlignCenter)
        slot_lbl.setFixedSize(26, 26)
        slot_lbl.setStyleSheet(f"""
            color: #ffffff;
            background-color: {color};
            border-radius: 6px;
            font-weight: bold;
            font-size: 10pt;
        """)
        layout.addWidget(slot_lbl, 0)

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        self.name_lbl = QLabel('No IR assigned')
        self.name_lbl.setStyleSheet(f"color: {TEXT_MAIN}; font-weight: 600; font-size: 9.5pt;")
        info_col.addWidget(self.name_lbl)

        self.meta_lbl = QLabel('Select a row in the library to assign')
        self.meta_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8pt; font-family: {FONT_FAMILY_MONO};")
        info_col.addWidget(self.meta_lbl)

        layout.addLayout(info_col, 1)

        # Validity Chip
        self.chip = ValidityChip('Empty', state='unknown')
        layout.addWidget(self.chip, 0)

        # Assign button
        self.set_btn = QPushButton(f'Set {slot} ← Sel')
        self.set_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_MAIN};
                border: 1px solid {BORDER_CARD};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 8.5pt;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #2a2a2a;
                border-color: {color};
            }}
        """)
        self.set_btn.clicked.connect(self.set_requested.emit)
        layout.addWidget(self.set_btn, 0)

    def set_record(self, rec: AnalysisResult | None) -> None:
        if rec is None:
            self.name_lbl.setText('No IR assigned')
            self.name_lbl.setToolTip('')
            self.meta_lbl.setText('Select a row in the library to assign')
            self.chip.set_state('unknown', 'Empty')
            return

        name = _short_name(rec.path)
        self.name_lbl.setText(name)
        self.name_lbl.setToolTip(rec.path)
        ch_str = 'Mono' if rec.channels == 1 else 'Stereo'
        score_str = f'Tone RMS: {rec.score:.1f} dB · ' if rec.score is not None else ''
        self.meta_lbl.setText(f"{score_str}{rec.sample_rate} Hz · {ch_str} · {rec.effective_length_ms:.0f} ms")
        self.chip.set_state('valid', 'Loaded')


class ABHeaderDeck(QWidget):
    """Dual deck header combining Card A, Swap button, and Card B."""

    set_a_requested = Signal()
    set_b_requested = Signal()
    swap_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.card_a = IRDeckCard('A', color=COLOR_IR_A)
        self.card_a.set_requested.connect(self.set_a_requested.emit)
        layout.addWidget(self.card_a, 1)

        self.swap_btn = QPushButton('⇄')
        self.swap_btn.setToolTip('Swap A and B')
        self.swap_btn.setFixedSize(36, 36)
        self.swap_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SURFACE_RAISED};
                color: {ACCENT_GOLD};
                border: 1px solid {BORDER_CARD};
                border-radius: 18px;
                font-size: 14pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2a2a2a;
                border-color: {ACCENT_GOLD};
            }}
        """)
        self.swap_btn.clicked.connect(self.swap_requested.emit)
        layout.addWidget(self.swap_btn, 0)

        self.card_b = IRDeckCard('B', color=COLOR_IR_B)
        self.card_b.set_requested.connect(self.set_b_requested.emit)
        layout.addWidget(self.card_b, 1)

    def set_a(self, rec: AnalysisResult | None) -> None:
        self.card_a.set_record(rec)

    def set_b(self, rec: AnalysisResult | None) -> None:
        self.card_b.set_record(rec)
