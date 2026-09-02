"""U04: middle-elided IR names with full-path accessibility.

Long IR names get clipped at the tail by default, so A/B cards and table
cells that share a long prefix end up looking identical. These widgets
middle-elide (keep head + identifiable tail such as mic/position) and expose
the full path through tooltip / accessible description without touching the
underlying record path.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QLabel, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem)


class MiddleElideLabel(QLabel):
    """QLabel that middle-elides its text to the current widget width.

    The displayed text (usually the file name) is elided keeping the head and
    the tail; the full path is carried separately for tooltip and
    accessibility, so a colour-blind or screen-reader user still sees which
    IR this card represents.
    """

    def __init__(self, text: str = '', parent=None):
        super().__init__(text, parent)
        self._display_text = text or ''

    def setPath(self, path: str) -> None:
        """Attach the full path for tooltip/accessibility (display text unchanged)."""
        self.setToolTip(path or '')
        self.setAccessibleDescription(path or '')
        self.setAccessibleName(path or '')

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        self._display_text = text or ''
        super().setText(self._display_text)
        self.update()

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._elide()

    def _elide(self) -> None:
        if not self._display_text:
            return
        margins = self.contentsMargins()
        avail = self.width() - margins.left() - margins.right()
        if avail < 8:
            return
        elided = self.fontMetrics().elidedText(
            self._display_text, Qt.ElideMiddle, avail)
        if elided != super().text():
            super().setText(elided)


class MiddleElideDelegate(QStyledItemDelegate):
    """Table delegate that middle-elides cell text (Name column) to its width."""

    def paint(self, painter, option, index) -> None:  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if opt.text:
            fm = opt.fontMetrics
            avail = opt.rect.width() - 4
            if avail > 8:
                opt.text = fm.elidedText(opt.text, Qt.ElideMiddle, avail)
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)