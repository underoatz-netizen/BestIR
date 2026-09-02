"""Spectrogram comparison view: A, B and difference heatmaps (WP-07).

B15: A, B and Difference render on the shared reference grid produced by
``compare_spectrograms`` (app/extensions/spectrogram.py) — identical time and
frequency axes, one common dB reference, a diverging difference scale centred
at zero, and an explicit reason instead of a blank panel whenever the pair
cannot be compared.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from app.extensions.spectrogram import (compare_spectrograms,
                                        spectrogram_error)

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_DIFF, COLOR_IR_A,
                          COLOR_IR_B, FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY,
                          SURFACE_CARD, SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)

_TICKS = [(20, '20'), (50, '50'), (100, '100'), (200, '200'), (500, '500'),
          (1000, '1k'), (2000, '2k'), (5000, '5k'), (10000, '10k'), (20000, '20k')]

_LUT = None
_DIFF_LUT = None

# U03: shared Boro styling for the visibility / dB-range selectors.
_COMBO_QSS = f"""
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
"""

_VISIBILITY_OPTIONS = (('all', 'All panels'), ('A', 'IR A only'),
                       ('B', 'IR B only'), ('diff', 'Difference only'))
_DB_RANGE_OPTIONS = (40, 50, 60, 70, 80)


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


def _diff_lut():
    """Diverging blue → neutral → orange scale, continuous through zero."""
    global _DIFF_LUT
    if _DIFF_LUT is None:
        lut = np.zeros((256, 3), dtype=np.ubyte)
        for i in range(256):
            v = i / 255.0          # 0..1 across -max..+max
            if v < 0.5:
                t = v / 0.5        # 0..1 from -max to 0
                lut[i] = [(1 - t) * 12 + t * 46,
                          (1 - t) * 22 + t * 46,
                          (1 - t) * 82 + t * 48]
            else:
                t = (v - 0.5) / 0.5  # 0..1 from 0 to +max
                lut[i] = [(1 - t) * 46 + t * 215,
                          (1 - t) * 46 + t * 72,
                          (1 - t) * 48 + t * 28]
        _DIFF_LUT = lut
    return _DIFF_LUT


def _heatmap(mag, freqs, times_ms, lut, levels):
    """ImageItem for one matrix on an explicit (log-freq, linear-time) grid."""
    img = pg.ImageItem(axisOrder='row-major')
    nf, nt = mag.shape
    x0 = float(np.log10(freqs[0]))
    x1 = float(np.log10(freqs[-1]))
    t0 = float(times_ms[0])
    t1 = float(times_ms[-1]) if nt > 1 else t0 + 1.0
    img.setImage(mag.T)
    img.setRect(x0, t0, (x1 - x0) * nf / (nf - 1) if nf > 1 else 1.0,
                (t1 - t0) * nt / (nt - 1) if nt > 1 else 1.0)
    img.setLookupTable(lut)
    img.setLevels(levels)
    return img


def _diff_scale(diff: np.ndarray) -> float:
    """Symmetric difference scale: max |dB| rounded up to a 5 dB multiple."""
    vals = diff[np.isfinite(diff)]
    if not len(vals):
        return 5.0
    m = float(np.max(np.abs(vals)))
    return max(5.0, float(np.ceil(m / 5.0) * 5.0))


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
        self._cards = {}
        self._pair_unavailable = False
        self._last_pair = None
        self._last_dyn = 60.0
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # U03: control row — panel visibility + shared dB-range rerender.
        controls = QHBoxLayout()
        controls.setSpacing(6)
        show_lbl = QLabel('Show:')
        show_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8.5pt;")
        controls.addWidget(show_lbl)
        self.view_selector = QComboBox()
        for value, label in _VISIBILITY_OPTIONS:
            self.view_selector.addItem(label, value)
        self.view_selector.setCurrentIndex(0)   # 'all' before any signal
        self.view_selector.setStyleSheet(_COMBO_QSS)
        self.view_selector.setToolTip(
            'Choose which spectrogram panels are visible. Hidden panels keep '
            'their rendered heatmap (axes stay shared).')
        controls.addWidget(self.view_selector)

        range_lbl = QLabel('dB range:')
        range_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8.5pt;")
        controls.addWidget(range_lbl)
        self.range_selector = QComboBox()
        for value in _DB_RANGE_OPTIONS:
            self.range_selector.addItem(f'{value} dB', value)
        self.range_selector.setCurrentIndex(2)  # 60 dB default
        self.range_selector.setStyleSheet(_COMBO_QSS)
        self.range_selector.setToolTip(
            'Shared dB window below the common reference; rerenders the A/B '
            'heatmaps on the same shared grid (Difference keeps its own '
            'symmetric scale).')
        controls.addWidget(self.range_selector)
        controls.addStretch(1)
        main_layout.addLayout(controls, 0)

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
            self._cards[key] = card
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

        # U03: user controls rerender on the cached pair only — they never
        # recompute the comparison themselves (B15 logic stays untouched).
        self.view_selector.currentIndexChanged.connect(self._apply_visibility)
        self.range_selector.currentIndexChanged.connect(self._on_range_changed)

    # ---- U03 controls -------------------------------------------------------
    def _apply_visibility(self, *_):
        """Show/hide the A/B/Diff cards; hidden panels keep their heatmap and
        the shared axes (visibility is purely a display concern)."""
        choice = self.view_selector.currentData()
        for key, card in self._cards.items():
            card.setVisible(choice == 'all' or choice == key)

    def _on_range_changed(self, *_):
        """Rerender the cached pair with the selected shared dB window."""
        if self._last_pair is None:
            return
        dyn = float(self.range_selector.currentData())
        self._last_dyn = dyn
        self.show_pair(self._last_pair[0], self._last_pair[1], dyn=dyn)

    # ---- rendering helpers -------------------------------------------------
    @staticmethod
    def _set_axes(plot: pg.PlotWidget, freqs, times_ms):
        x0 = float(np.log10(freqs[0]))
        x1 = float(np.log10(freqs[-1]))
        t0 = float(times_ms[0])
        t1 = float(times_ms[-1]) if len(times_ms) > 1 else t0 + 1.0
        plot.setXRange(x0, x1, padding=0.02)
        plot.setYRange(t0, t1, padding=0.02)
        plot.disableAutoRange()

    def _set_shared_axes(self, freqs, times_ms):
        for plot in self._plots.values():
            self._set_axes(plot, freqs, times_ms)

    def _plot_message(self, plot: pg.PlotWidget, text: str, color):
        item = pg.TextItem(text, color=color, anchor=(0.5, 0.5))
        plot.addItem(item)
        (x0, x1), (y0, y1) = plot.getViewBox().viewRange()
        item.setPos((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def _render_own(self, plot: pg.PlotWidget, spec, dyn: float):
        """Render a single valid side on its own native grid (pair not
        comparable — no shared grid exists)."""
        mag = np.asarray(spec.magnitude_db, dtype=float)
        valid = getattr(spec, 'valid_mask', None)
        if valid is not None and len(valid) == mag.shape[0]:
            mag = np.where(np.asarray(valid, dtype=bool)[:, None], mag, np.nan)
        freqs = np.asarray(spec.freqs, dtype=float)
        times = np.asarray(spec.times_ms, dtype=float)
        plot.addItem(_heatmap(mag, freqs, times, _lut(), (-dyn, 0.0)))
        self._set_axes(plot, freqs, times)

    # ---- public API --------------------------------------------------------
    def show_pair(self, spec_a, spec_b, dyn: float = 60.0):
        self._last_pair = (spec_a, spec_b)
        self._last_dyn = dyn
        for plot in self._plots.values():
            plot.clear()
        cmp = compare_spectrograms(spec_a, spec_b)
        self._pair_unavailable = not cmp.available
        if not cmp.available:
            self._show_pair_unavailable(spec_a, spec_b, cmp.reason, dyn)
            return

        mag_a = np.where(cmp.valid_a, cmp.magnitude_a_db, np.nan)
        mag_b = np.where(cmp.valid_b, cmp.magnitude_b_db, np.nan)
        diff = np.where(cmp.valid_diff, cmp.diff_db, np.nan)
        levels = (cmp.ref_db - dyn, cmp.ref_db)
        self._plots['A'].addItem(
            _heatmap(mag_a, cmp.freqs, cmp.times_ms, _lut(), levels))
        self._plots['B'].addItem(
            _heatmap(mag_b, cmp.freqs, cmp.times_ms, _lut(), levels))
        dmax = _diff_scale(cmp.diff_db)
        self._plots['diff'].addItem(
            _heatmap(diff, cmp.freqs, cmp.times_ms, _diff_lut(),
                     (-dmax, dmax)))
        # identical displayed axes on all three panels
        self._set_shared_axes(cmp.freqs, cmp.times_ms)
        self._diff_label.setText(
            f'Shared grid {cmp.overlap_time_ms[0]:.1f}–{cmp.overlap_time_ms[1]:.1f} ms, '
            f'{cmp.overlap_freq_hz[0]:.0f}–{cmp.overlap_freq_hz[1]:.0f} Hz; '
            f'A/B dB reference {cmp.ref_db:+.1f} dB; difference ±{dmax:.0f} dB '
            f'centred at 0 (orange = A louder, blue = B louder).')

    def _show_pair_unavailable(self, spec_a, spec_b, reason: str,
                               dyn: float):
        """Explicit no-data panels: render each individually-valid side on
        its own grid and explain the pair incompatibility in the footer."""
        messages = []
        for key, spec in (('A', spec_a), ('B', spec_b)):
            err = spectrogram_error(spec)
            if err is not None:
                messages.append(f'No data for IR {key}: {err}.')
                self._plot_message(self._plots[key], f'IR {key}: {err}',
                                   TEXT_MUTED)
            else:
                self._render_own(self._plots[key], spec, dyn)
        self._plot_message(self._plots['diff'], 'Difference unavailable',
                           TEXT_MUTED)
        messages.append(f'Difference unavailable: {reason}.')
        self._diff_label.setText(' '.join(messages))

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