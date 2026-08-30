"""Spectrogram comparison view: A, B and difference heatmaps (WP-07)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.styles import SURFACE

_TICKS = [(20, '20'), (50, '50'), (100, '100'), (200, '200'), (500, '500'),
          (1000, '1k'), (2000, '2k'), (5000, '5k'), (10000, '10k'), (20000, '20k')]

_LUT = None


def _lut():
    global _LUT
    if _LUT is None:
        lut = np.zeros((256, 3), dtype=np.ubyte)
        for i in range(256):
            f = i / 255.0
            lut[i] = [int(20 + 235 * f ** 1.5), int(30 + 180 * f ** 1.2),
                      int(45 + 200 * f)]
        _LUT = lut
    return _LUT


def _heatmap(result, dyn):
    img = pg.ImageItem(axisOrder='row-major')
    mag = np.asarray(result.magnitude_db, dtype=float)
    nf, nt = mag.shape
    x0 = float(np.log10(result.freqs[0]))
    x1 = float(np.log10(result.freqs[-1]))
    t0 = float(result.times_ms[0])
    t1 = float(result.times_ms[-1]) if nt > 1 else t0 + 1.0
    img.setImage(mag.T)
    img.setRect(x0, t0, (x1 - x0) * nf / (nf - 1) if nf > 1 else 1.0,
                (t1 - t0) * nt / (nt - 1) if nt > 1 else 1.0)
    img.setLookupTable(_lut())
    img.setLevels((-dyn, 0))
    return img


def _style(plot: pg.PlotWidget):
    ax = plot.getAxis('bottom')
    ax.setTicks([[(float(np.log10(v)), lbl) for v, lbl in _TICKS]])
    plot.setLabel('bottom', 'Frequency (Hz)')
    plot.setLabel('left', 'Time (ms)')
    plot.invertY(True)
    plot.showGrid(x=False, y=False)


class SpectrogramView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plots = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for name, title in (('A', 'A'), ('B', 'B'), ('diff', 'A − B')):
            col = QVBoxLayout()
            col.addWidget(QLabel(title))
            plot = pg.PlotWidget(background=SURFACE)
            _style(plot)
            self._plots[name] = plot
            col.addWidget(plot)
            container = QWidget()
            container.setLayout(col)
            layout.addWidget(container, 1)
        self._diff_label = QLabel('')
        layout_of_self = self.layout()
        layout_of_self.addWidget(self._diff_label)

    def show_pair(self, spec_a, spec_b, dyn: float = 60.0):
        self._plots['A'].clear()
        self._plots['B'].clear()
        self._plots['diff'].clear()
        if spec_a is not None:
            self._plots['A'].addItem(_heatmap(spec_a, dyn))
        if spec_b is not None:
            self._plots['B'].addItem(_heatmap(spec_b, dyn))
        text = ''
        if spec_a is not None and spec_b is not None:
            fa, fb = spec_a.freqs, spec_b.freqs
            ta, tb = spec_a.times_ms, spec_b.times_ms
            if len(fa) == len(fb) and len(ta) == len(tb) and \
                    np.allclose(fa, fb) and np.allclose(ta, tb):
                diff = np.asarray(spec_a.magnitude_db) - \
                    np.asarray(spec_b.magnitude_db)
                img = pg.ImageItem(axisOrder='row-major')
                nf, nt = diff.shape
                x0 = float(np.log10(fa[0]))
                x1 = float(np.log10(fa[-1]))
                t0 = float(ta[0])
                t1 = float(ta[-1]) if nt > 1 else t0 + 1.0
                img.setImage(diff.T)
                img.setRect(x0, t0, (x1 - x0) * nf / (nf - 1) if nf > 1 else 1.0,
                            (t1 - t0) * nt / (nt - 1) if nt > 1 else 1.0)
                img.setLookupTable(_lut())
                img.setLevels((-15, 15))   # symmetric: positive = A brighter
                self._plots['diff'].addItem(img)
                text = ('Difference scale ±15 dB — bright: A has more energy '
                        'there; dark: B has more.')
        self._diff_label.setText(text)

    def show_metrics(self, metrics_a: dict, metrics_b: dict):
        def line(m):
            if not m or not m.get('persistence_valid'):
                return 'persistence: n/a'
            return (f"{m.get('persistence_band_hz')} excess "
                    f"{m.get('persistence_excess_db'):.1f} dB, "
                    f"duration {m.get('persistence_duration_ms'):.0f} ms, "
                    f"ridge {m.get('persistence_ridge_hz'):.0f} Hz")
        self._diff_label.setText(f'A: {line(metrics_a)}   |   B: {line(metrics_b)}')
