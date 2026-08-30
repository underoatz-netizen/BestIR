"""ValidityChip: Boro-styled status pill displaying acoustic validity."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from ..styles_boro import (COLOR_INVALID, COLOR_INVALID_BG, COLOR_INVALID_BORDER,
                           COLOR_VALID, COLOR_VALID_BG, COLOR_VALID_BORDER,
                           COLOR_WARN, COLOR_WARN_BG, COLOR_WARN_BORDER,
                           FONT_FAMILY_PRIMARY)


class ValidityChip(QLabel):
    """Compact status chip indicating validity with tooltips and high-contrast styling."""

    def __init__(self, text: str = 'Valid', state: str = 'valid', tooltip: str = '', parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFont_()
        self.set_state(state, text, tooltip)

    def setFont_(self):
        f = self.font()
        f.setPointSize(8)
        f.setBold(True)
        self.setFont(f)

    def set_state(self, state: str = 'valid', text: str | None = None, tooltip: str = '') -> None:
        state = state.lower()
        if text is not None:
            self.setText(text)
        if tooltip:
            self.setToolTip(tooltip)

        if state in ('valid', 'ok', 'clean'):
            fg, bg, bd = COLOR_VALID, COLOR_VALID_BG, COLOR_VALID_BORDER
            icon = '✓ ' if not self.text().startswith('✓') else ''
        elif state in ('warn', 'warning', 'low_confidence', 'truncated'):
            fg, bg, bd = COLOR_WARN, COLOR_WARN_BG, COLOR_WARN_BORDER
            icon = '⚠️ ' if not self.text().startswith('⚠️') else ''
        elif state in ('invalid', 'error', 'noise_dominated', 'failed'):
            fg, bg, bd = COLOR_INVALID, COLOR_INVALID_BG, COLOR_INVALID_BORDER
            icon = '✕ ' if not self.text().startswith('✕') else ''
        else:
            fg, bg, bd = '#949494', '#1f1f1f', '#333333'
            icon = ''

        if icon and not any(self.text().startswith(x) for x in ('✓', '⚠️', '✕')):
            self.setText(icon + self.text())

        self.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                border: 1px solid {bd};
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 8pt;
                font-weight: 600;
            }}
        """)
