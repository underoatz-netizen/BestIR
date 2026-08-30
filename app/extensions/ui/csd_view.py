"""CSD view: renderer selection + band-decay numeric panel (WP-07).

Enhanced with Boro UI styling and numeric evidence cards.
"""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QTextEdit, QVBoxLayout, QWidget)

from .renderers.csd_base import try_opengl_renderer
from .renderers.csd_fallback import FallbackCsdRenderer, RidgeCsdRenderer
from .styles_boro import (ACCENT_GOLD, BORDER_CARD, FONT_FAMILY_MONO,
                          FONT_FAMILY_PRIMARY, SURFACE_CARD, SURFACE_RAISED,
                          TEXT_MAIN, TEXT_MUTED)
from .widgets.validity_chip import ValidityChip


class CsdView(QWidget):
    """Heatmap CSD (OpenGL surface when available) + band-decay readouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = None
        self._using_gl = False
        gl = try_opengl_renderer()
        self._plot = pg.PlotWidget(background=SURFACE_CARD)
        self._plot.setMouseEnabled(x=True, y=True)
        if gl is not None:
            self._renderer = gl
            self._using_gl = True
        else:
            self._renderer = FallbackCsdRenderer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Plot on top
        layout.addWidget(self._plot, 3)

        # Numeric Evidence section
        bottom_box = QFrame()
        bottom_box.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        b_lay = QVBoxLayout(bottom_box)
        b_lay.setContentsMargins(8, 6, 8, 6)
        b_lay.setSpacing(4)

        header_row = QHBoxLayout()
        hdr_lbl = QLabel('Band Decay & Tail Persistence (Numeric Evidence):')
        hdr_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        header_row.addWidget(hdr_lbl, 1)

        renderer_badge = ValidityChip(
            text='OpenGL 3D' if self._using_gl else '2D Fallback',
            state='valid' if self._using_gl else 'warn'
        )
        header_row.addWidget(renderer_badge, 0)
        b_lay.addLayout(header_row)

        self._decay_text = QTextEdit()
        self._decay_text.setReadOnly(True)
        self._decay_text.setMaximumHeight(90)
        self._decay_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER_CARD};
                border-radius: 6px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
                padding: 6px;
            }}
        """)
        b_lay.addWidget(self._decay_text)
        layout.addWidget(bottom_box, 1)

    @property
    def using_opengl(self) -> bool:
        return self._using_gl

    def show_csd(self, csd_result, mode: str = 'A') -> None:
        if csd_result is None:
            return
        if not self._using_gl:
            self._renderer.render(self._plot, csd_result, mode)
        else:
            self._renderer.render(self._plot, csd_result, mode)

        lines = []
        for name, curve in (csd_result.band_decay or {}).items():
            d10 = csd_result.metrics.get(f'D10_{name}_ms')
            d20 = csd_result.metrics.get(f'D20_{name}_ms')
            d30 = csd_result.metrics.get(f'D30_{name}_ms')
            fmt = (lambda v: f'{v:.0f} ms' if isinstance(v, (int, float))
                   else 'n/a')
            valid20 = csd_result.metrics.get(f'D20_{name}_valid', False)
            valid_tag = ' ✓' if valid20 else ' (invalid/noisy)'
            lines.append(f'• {name} Hz Band:  D10 = {fmt(d10):<7}  '
                         f'D20 = {fmt(d20):<7}{valid_tag:<18}  '
                         f'D30 = {fmt(d30)}')
        self._decay_text.setPlainText('\n'.join(lines) or 'No band decay data.')
