"""CSD view: renderer selection + band-decay numeric panel (WP-07)."""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from .renderers.csd_base import try_opengl_renderer
from .renderers.csd_fallback import FallbackCsdRenderer, RidgeCsdRenderer


class CsdView(QWidget):
    """Heatmap CSD (OpenGL surface when available) + band-decay readouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = None
        self._using_gl = False
        gl = try_opengl_renderer()
        self._plot = pg.PlotWidget()
        self._plot.setMouseEnabled(x=True, y=True)
        if gl is not None:
            self._renderer = gl
            self._using_gl = True
        else:
            self._renderer = FallbackCsdRenderer()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot, 3)
        self._decay_text = QTextEdit()
        self._decay_text.setReadOnly(True)
        self._decay_text.setMaximumHeight(120)
        layout.addWidget(QLabel('Band decay (numeric evidence):'), 0)
        layout.addWidget(self._decay_text, 1)

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
            lines.append(f'{name} Hz: D10={fmt(d10)} D20={fmt(d20)}'
                         f'{"" if valid20 else " (invalid)"} D30={fmt(d30)}')
        self._decay_text.setPlainText('\n'.join(lines) or 'no band data')
