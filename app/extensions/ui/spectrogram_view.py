"""Spectrogram comparison view: A, B and difference heatmaps (WP-07).

Enhanced with Boro UI styling, color-coded panel headers, and symmetric difference scale.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from app.extensions.contracts import AnalysisStatus

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_DIFF, COLOR_IR_A,
                          COLOR_IR_B, FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                          SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)

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


def _status_text(result) -> str:
    status = getattr(result, 'status', None)
    value = getattr(status, 'value', status)
    return str(value).replace('_', ' ') if value is not None else 'unavailable'


def _spectrogram_error(result) -> str | None:
    if result is None:
        return 'unavailable'
    if getattr(result, 'status', None) != AnalysisStatus.OK:
        return _status_text(result)
    if (getattr(result, 'magnitude_db', None) is None or
            getattr(result, 'freqs', None) is None or
            getattr(result, 'times_ms', None) is None):
        return 'missing spectrogram data'
    try:
        magnitude = np.asarray(result.magnitude_db, dtype=float)
        freqs = np.asarray(result.freqs, dtype=float)
        times = np.asarray(result.times_ms, dtype=float)
    except (TypeError, ValueError):
        return 'malformed spectrogram data'
    if magnitude.ndim != 2:
        return 'magnitude matrix is not two-dimensional'
    if freqs.ndim != 1 or not len(freqs):
        return 'frequency axis is missing or malformed'
    if times.ndim != 1 or not len(times):
        return 'time axis is missing or malformed'
    if magnitude.shape != (len(freqs), len(times)):
        return 'magnitude matrix does not match its axes'
    if (not np.all(np.isfinite(magnitude)) or
            not np.all(np.isfinite(freqs)) or not np.all(freqs > 0) or
            not np.all(np.isfinite(times))):
        return 'spectrogram data contains invalid values'
    if ((len(freqs) > 1 and np.any(np.diff(freqs) <= 0)) or
            (len(times) > 1 and np.any(np.diff(times) <= 0))):
        return 'spectrogram axes must increase'
    return None


def _style(plot: pg.PlotWidget):
    ax = plot.getAxis('bottom')
    ax.setTicks([[(float(np.log10(v)), lbl) for v, lbl in _TICKS]])
    plot.setLabel('bottom', 'Frequency (Hz)', color=TEXT_MUTED)
    plot.setLabel('left', 'Time (ms)', color=TEXT_MUTED)
    plot.invertY(True)
    plot.showGrid(x=False, y=False)


class SpectrogramView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plots = {}
        self._pair_unavailable = False
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # 3 Panels Row
        grid_row = QHBoxLayout()
        grid_row.setSpacing(6)

        configs = [
            ('A', 'Spectrogram: IR A', COLOR_IR_A),
            ('B', 'Spectrogram: IR B', COLOR_IR_B),
            ('diff', 'Difference: A − B', COLOR_DIFF),
        ]

        for key, title, color in configs:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {SURFACE_CARD};
                    border: 1px solid {BORDER_CARD};
                    border-radius: 8px;
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(6, 6, 6, 6)
            c_lay.setSpacing(4)

            hdr = QLabel(title)
            hdr.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 8.5pt;")
            c_lay.addWidget(hdr, 0)

            plot = pg.PlotWidget(background=SURFACE_CARD)
            _style(plot)
            self._plots[key] = plot
            c_lay.addWidget(plot, 1)

            grid_row.addWidget(card, 1)

        main_layout.addLayout(grid_row, 1)

        # Metrics / Difference explanation label at bottom
        self._diff_label = QLabel('')
        self._diff_label.setStyleSheet(f"""
            QLabel {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 6px;
                padding: 6px 10px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8pt;
            }}
        """)
        main_layout.addWidget(self._diff_label, 0)

    def show_pair(self, spec_a, spec_b, dyn: float = 60.0):
        self._plots['A'].clear()
        self._plots['B'].clear()
        self._plots['diff'].clear()
        error_a = _spectrogram_error(spec_a)
        error_b = _spectrogram_error(spec_b)
        self._pair_unavailable = bool(error_a or error_b)
        if error_a is None:
            self._plots['A'].addItem(_heatmap(spec_a, dyn))
        if error_b is None:
            self._plots['B'].addItem(_heatmap(spec_b, dyn))
        if self._pair_unavailable:
            messages = []
            if error_a is not None:
                messages.append(f'No data for IR A: {error_a}.')
            if error_b is not None:
                messages.append(f'No data for IR B: {error_b}.')
            messages.append('Difference unavailable.')
            self._diff_label.setText(' '.join(messages))
            return

        fa = np.asarray(spec_a.freqs, dtype=float)
        fb = np.asarray(spec_b.freqs, dtype=float)
        ta = np.asarray(spec_a.times_ms, dtype=float)
        tb = np.asarray(spec_b.times_ms, dtype=float)
        if not (len(fa) == len(fb) and len(ta) == len(tb) and
                np.allclose(fa, fb) and np.allclose(ta, tb)):
            self._pair_unavailable = True
            self._diff_label.setText(
                'Difference unavailable: IR A and IR B spectrogram axes do not match.')
            return

        diff = (np.asarray(spec_a.magnitude_db, dtype=float) -
                np.asarray(spec_b.magnitude_db, dtype=float))
        if not np.all(np.isfinite(diff)):
            self._pair_unavailable = True
            self._diff_label.setText(
                'Difference unavailable: spectrogram data contains invalid values.')
            return
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
        img.setLevels((-15, 15))
        self._plots['diff'].addItem(img)
        self._diff_label.setText(
            'Difference scale +/-15 dB: Bright = IR A has more persistent energy, '
            'Dark = IR B has more.')

    def show_metrics(self, metrics_a: dict, metrics_b: dict):
        if self._pair_unavailable:
            return

        def line(m):
            if not m or not m.get('persistence_valid'):
                return 'persistence: n/a'
            return (f"{m.get('persistence_band_hz')} excess "
                    f"{m.get('persistence_excess_db'):.1f} dB, "
                    f"duration {m.get('persistence_duration_ms'):.0f} ms, "
                    f"ridge {m.get('persistence_ridge_hz'):.0f} Hz")
        self._diff_label.setText(f'IR A: {line(metrics_a)}   |   IR B: {line(metrics_b)}')
