"""Deterministic 2D fallback CSD renderer: heatmap + stacked ridge (WP-07)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from app.ui.styles import SURFACE

_TICKS = [(20, '20'), (50, '50'), (100, '100'), (200, '200'), (500, '500'),
          (1000, '1k'), (2000, '2k'), (5000, '5k'), (10000, '10k'), (20000, '20k')]


class FallbackCsdRenderer:
    name = '2d'

    def supports(self) -> bool:
        return True

    def render(self, plot_widget, csd_result, mode: str = 'A') -> None:
        plot_widget.clear()
        mag = np.asarray(csd_result.magnitude_db, dtype=float)
        nf, nt = mag.shape
        x0 = float(np.log10(csd_result.freqs[0]))
        x1 = float(np.log10(csd_result.freqs[-1]))
        t0 = float(csd_result.times_ms[0])
        t1 = float(csd_result.times_ms[-1]) if nt > 1 else t0 + 1.0

        img = pg.ImageItem(axisOrder='row-major')
        img.setImage(mag.T)                     # rows = time, cols = freq
        img.setRect(x0, t0, (x1 - x0) * nf / (nf - 1) if nf > 1 else x1 - x0,
                    (t1 - t0) * nt / (nt - 1) if nt > 1 else t1 - t0)
        lut = _gray_lut()
        img.setLookupTable(lut)
        img.setLevels((-csd_result.cfg.dynamic_range_db, 0))
        plot_widget.addItem(img)

        ax = plot_widget.getAxis('bottom')
        ax.setTicks([[(float(np.log10(v)), lbl) for v, lbl in _TICKS]])
        plot_widget.setLabel('bottom', 'Frequency (Hz)')
        plot_widget.setLabel('left', 'Time after onset (ms)')
        plot_widget.invertY(True)


def _gray_lut():
    lut = np.zeros((256, 3), dtype=np.ubyte)
    for i in range(256):
        f = i / 255.0
        lut[i] = [int(30 + 200 * f ** 1.4), int(34 + 190 * f ** 1.2),
                  int(40 + 200 * f)]
    return lut


class RidgeCsdRenderer:
    """Stacked-ridge fallback: one offset curve per time gate."""

    name = 'ridge'

    def supports(self) -> bool:
        return True

    def render(self, plot_widget, csd_result, mode: str = 'A') -> None:
        plot_widget.clear()
        mag = np.asarray(csd_result.magnitude_db, dtype=float)
        nf, nt = mag.shape
        lx = np.log10(np.asarray(csd_result.freqs, dtype=float))
        step = max(1, nt // 40)
        for j in range(0, nt, step):
            y = mag[:, j]
            offset = -j / max(1, nt // step) * 6.0
            plot_widget.plot(x=lx, y=y + offset,
                             pen=pg.mkPen(QColor(96, 181, 255, 160), width=1))
        ax = plot_widget.getAxis('bottom')
        ax.setTicks([[(float(np.log10(v)), lbl) for v, lbl in _TICKS]])
        plot_widget.setLabel('bottom', 'Frequency (Hz)')
        plot_widget.setLabel('left', 'Rel. level (dB), gates stacked downward')
