"""Spectrum plot: overlaid smoothed curves, target curve, tone-match overlays."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from app.core.analysis import CURVE_FREQS, AnalysisResult
from .styles import SURFACE

LOG_X = np.log10(CURVE_FREQS)
X_MIN, X_MAX = float(LOG_X[0]), float(LOG_X[-1])
MAX_CURVES = 600

_MAJOR = [20, 30, 50, 100, 200, 300, 500, 1000, 2000, 3000, 5000, 10000, 20000]
_MINOR = [40, 60, 70, 80, 150, 400, 600, 700, 1500, 4000, 6000, 7000, 15000]

_CURVE_PEN = pg.mkPen(QColor(120, 130, 145, 70), width=1)
_HOVER_PEN = pg.mkPen(QColor(255, 213, 79), width=2)
_SEL_PEN = pg.mkPen(QColor(80, 220, 140), width=3)
_TOP_PEN = pg.mkPen(QColor(96, 181, 255, 220), width=2)
_TARGET_PEN = pg.mkPen(QColor(255, 122, 90), width=2, style=Qt.DashLine)
_DI_PEN = pg.mkPen(QColor(255, 213, 79, 200), width=1.5)
_OUTPUT_PEN = pg.mkPen(QColor(64, 196, 255), width=2.5)


def _color_for(path: str) -> QColor:
    h = abs(hash(path))
    return QColor.fromHsv(h % 360, 150, 255)


class PlotPanel(pg.PlotWidget):
    curve_clicked = Signal(str)  # path of nearest curve on click

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground(SURFACE)
        pi = self.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.2)
        pi.setLabel('bottom', 'Frequency (Hz)')
        pi.setLabel('left', 'Magnitude (dB)')
        pi.setMouseEnabled(x=True, y=True)
        self.getAxis('bottom').setTicks([
            [(float(np.log10(v)), f'{v:,}') for v in _MAJOR],
            [(float(np.log10(v)), '') for v in _MINOR],
        ])
        # Fixed-range mode: auto-range would re-fit on every hover-label move
        # and drift the view endlessly. We fit the view ourselves in
        # _fit_view() and never touch it again once the user zooms/pans.
        self._manual_range = False
        vb = pi.vb
        vb.sigRangeChangedManually.connect(self._on_manual_range)
        vb.setRange(xRange=(X_MIN, X_MAX), yRange=(-48.0, 15.0), padding=0)

        self._items: dict[str, pg.PlotDataItem] = {}
        self._records: list[AnalysisResult] = []
        self._selected: set[str] = set()
        self._top: set[str] = set()
        self._hover_path: str | None = None
        self._hover_label = pg.TextItem(color='#ffd54f', anchor=(0, 1))
        self._hover_label.setZValue(50)
        self.addItem(self._hover_label)

        self._target_item = pg.PlotDataItem(pen=_TARGET_PEN)
        self._target_item.setZValue(40)
        self.addItem(self._target_item)
        self._target_visible = False

        self._di_item = pg.PlotDataItem(pen=_DI_PEN)
        self._di_item.setZValue(35)
        self._di_item.hide()
        self.addItem(self._di_item)
        self._output_item = pg.PlotDataItem(pen=_OUTPUT_PEN)
        self._output_item.setZValue(38)
        self._output_item.hide()
        self.addItem(self._output_item)

        self.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.scene().sigMouseClicked.connect(self._on_clicked)

    # ---- view fitting -----------------------------------------------------------
    def _on_manual_range(self, *_):
        self._manual_range = True

    def _fit_view(self) -> None:
        """Fit y-range to the visible curves (never after the user zooms/pans)."""
        if self._manual_range:
            return
        ys = [item.yData for item in self._items.values()
              if item.isVisible() and item.yData is not None and len(item.yData)]
        for extra in (self._di_item, self._output_item, self._target_item):
            if extra.isVisible() and extra.yData is not None and len(extra.yData):
                ys.append(extra.yData)
        if not ys:
            return
        all_y = np.concatenate(ys)
        lo, hi = float(all_y.min()), float(all_y.max())
        pad = max((hi - lo) * 0.05, 2.0)
        self.getPlotItem().vb.setRange(xRange=(X_MIN, X_MAX),
                                       yRange=(lo - pad, hi + pad), padding=0)

    # ---- curves --------------------------------------------------------------
    def set_records(self, records: list[AnalysisResult]) -> None:
        self._records = records
        shown = records[:MAX_CURVES]
        alive = {r.path for r in shown}
        for path in list(self._items):
            if path not in alive:
                self.removeItem(self._items.pop(path))
        for r in shown:
            if r.path not in self._items:
                item = pg.PlotDataItem(x=LOG_X, y=r.curve_db, pen=_CURVE_PEN)
                item.setZValue(5)
                self.addItem(item)
                self._items[r.path] = item
        self._refresh_pens()
        self._update_hover_label(None)
        self._fit_view()

    def set_selected(self, paths: set[str]) -> None:
        self._selected = paths
        self._refresh_pens()

    def set_top(self, paths: list[str]) -> None:
        self._top = set(paths)
        self._refresh_pens()

    def _refresh_pens(self) -> None:
        for path, item in self._items.items():
            if path in self._selected:
                item.setPen(_SEL_PEN)
                item.setZValue(30)
            elif path in self._top:
                item.setPen(_TOP_PEN)
                item.setZValue(15)
            elif path == self._hover_path:
                item.setPen(_HOVER_PEN)
                item.setZValue(20)
            else:
                item.setPen(_CURVE_PEN)
                item.setZValue(5)

    # ---- target curve ----------------------------------------------------------
    def show_target(self, target_db: np.ndarray | None) -> None:
        self._target_visible = target_db is not None
        self._target_item.setVisible(target_db is not None)
        if target_db is not None:
            self._target_item.setData(x=LOG_X, y=target_db)
        self._fit_view()

    # ---- tone-match overlays -----------------------------------------------------
    def show_di_curve(self, curve: np.ndarray | None) -> None:
        self._di_item.setVisible(curve is not None)
        if curve is not None:
            self._di_item.setData(x=LOG_X, y=curve)
        self._fit_view()

    def show_output_curve(self, curve: np.ndarray | None) -> None:
        self._output_item.setVisible(curve is not None)
        if curve is not None:
            self._output_item.setData(x=LOG_X, y=curve)
        self._fit_view()

    # ---- mouse ----------------------------------------------------------------
    def _view_pos(self, scene_pos):
        vb = self.getPlotItem().vb
        return vb.mapSceneToView(scene_pos)

    def _nearest_curve(self, vx: float, vy: float) -> str | None:
        best, best_d = None, 1e9
        yr = self.getPlotItem().vb.viewRange()[1]
        yscale = max(abs(yr[1] - yr[0]), 1.0)
        for r in self._records[:MAX_CURVES]:
            d = (LOG_X - vx) ** 2 + ((r.curve_db - vy) / yscale * 8.0) ** 2
            i = int(np.argmin(d))
            if d[i] < best_d:
                best_d, best = float(d[i]), r.path
        return best

    def _on_mouse_moved(self, scene_pos) -> None:
        p = self._view_pos(scene_pos)
        if not (X_MIN <= p.x() <= X_MAX):
            self._update_hover_label(None)
            return
        path = self._nearest_curve(p.x(), p.y())
        if path != self._hover_path:
            self._hover_path = path
            self._refresh_pens()
            self._update_hover_label(path)

    def _update_hover_label(self, path: str | None) -> None:
        if path is None:
            self._hover_label.setText('')
            return
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        vr = self.getPlotItem().vb.viewRange()
        self._hover_label.setPos(vr[0][0] + 0.03, vr[1][1])
        self._hover_label.setText(name, color='#ffd54f')

    def _on_clicked(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        p = self._view_pos(event.scenePos())
        path = self._nearest_curve(p.x(), p.y())
        if path:
            self.curve_clicked.emit(path)
