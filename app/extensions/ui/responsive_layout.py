"""Wave 5 / U01 foundation: responsive layout adapter for the extended window.

Extension-only. Wraps three legacy regions for narrow (1280x720-class)
windows WITHOUT editing app/ui:

* inspector drawer  — the right InspectorPanel collapses to a toolbar toggle
                      and reopens with its previous splitter sizes;
* action wrap       — extension actions live in a flow container that wraps
                      to extra rows when the window is too narrow;
* filter wrap       — the secondary library filters (SR / Ch / Tags / Flat)
                      move into an overflow popup, leaving Search + Clear in
                      the row; the exact original row order is restored when
                      the window widens again.

All three behaviors are opt-in via ExtendedMainWindow and are instance-local:
no legacy module globals, layouts or widgets are modified at source level.
"""
from __future__ import annotations

from PySide6.QtCore import (QEvent, QObject, QPoint, QRect, QSize, Qt)
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLayout, QMenu,
                               QSplitter, QToolBar, QToolButton, QWidget,
                               QWidgetAction)


class _FlowLayout(QLayout):
    """Minimal flow layout: children wrap onto new rows when space runs out."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 4):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):  # noqa: N802 (Qt override)
        self._items.append(item)

    def count(self) -> int:  # noqa: A003 (Qt API name)
        return len(self._items)

    def itemAt(self, index):  # noqa: N802 (Qt override)
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):  # noqa: N802 (Qt override)
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 (Qt override)
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt override)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt override)
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:  # noqa: N802 (Qt override)
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):  # noqa: N802 (Qt override)
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802 (Qt override)
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self.spacing()
            if (next_x - self.spacing() > effective.right() + 1
                    and line_height > 0):
                x = effective.x()
                y += line_height + self.spacing()
                next_x = x + hint.width() + self.spacing()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class FlowContainer(QWidget):
    """Widget whose children wrap onto extra rows when it gets too narrow."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setLayout(_FlowLayout(self))


class ResponsiveLayoutAdapter(QObject):
    """Responsive wrapping for the extended legacy window (U01 foundation).

    Attach to an ExtendedMainWindow; the adapter owns the extension toolbar
    (actions in a wrapping flow container) and watches window width to:

    * collapse the inspector into a drawer below ``responsive_width``,
    * move the secondary library filters into an overflow popup below it,
    * let the action flow wrap to extra rows as the toolbar narrows.
    """

    RESPONSIVE_WIDTH = 1280

    # LibraryPanel attribute -> popup row label for the movable filters.
    FILTER_WIDGETS = ('sr_combo', 'ch_combo', 'tag_combo', 'flat_spin')
    FILTER_LABELS = {'sr_combo': 'SR', 'ch_combo': 'Ch',
                     'tag_combo': 'Tags', 'flat_spin': 'Flat ≤'}

    def __init__(self, window, actions=(), responsive_width: int = RESPONSIVE_WIDTH):
        super().__init__(window)
        self.window = window
        self.responsive_width = int(responsive_width)
        self._compact = False
        self._inspector_open = True
        self._inspector_sizes: list[int] | None = None
        self._filter_state = None  # (snapshot, menu, btn) while compact

        # ---- action wrap: flow container inside the extension toolbar -----
        self.flow = FlowContainer()
        from PySide6.QtWidgets import QSizePolicy
        self.flow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        for action in actions:
            btn = QToolButton()
            btn.setDefaultAction(action)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.flow.layout().addWidget(btn)

        # ---- inspector drawer toggle --------------------------------------
        self.btn_inspector = QToolButton()
        self.btn_inspector.setText('Inspector')
        self.btn_inspector.setToolTip('Show / hide the inspector drawer')
        self.btn_inspector.setCheckable(True)
        self.btn_inspector.toggled.connect(
            lambda checked: self.set_inspector_open(not checked))
        self.flow.layout().addWidget(self.btn_inspector)

        self.toolbar = QToolBar('Response tools')
        self.toolbar.setMovable(False)
        self.toolbar.addWidget(self.flow)
        window.addToolBar(self.toolbar)

        window.installEventFilter(self)
        self._apply_mode(window.width())

    # ---- mode switching -----------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if obj is self.window and event.type() == QEvent.Resize:
            self._apply_mode(self.window.width())
        return super().eventFilter(obj, event)

    def _apply_mode(self, width: int) -> None:
        compact = width < self.responsive_width
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self._wrap_filters()
            self.set_inspector_open(False)
        else:
            self._unwrap_filters()
            self.set_inspector_open(True)

    # ---- inspector drawer ----------------------------------------------------
    def is_compact(self) -> bool:
        return self._compact

    def inspector_open(self) -> bool:
        return self._inspector_open

    def toggle_inspector(self) -> None:
        self.set_inspector_open(not self._inspector_open)

    def set_inspector_open(self, open_: bool) -> None:
        open_ = bool(open_)
        self._inspector_open = open_
        self.btn_inspector.setChecked(not open_)
        splitter = self.window.centralWidget()
        inspector = self.window.inspector
        if open_:
            if not inspector.isVisible():
                inspector.show()
            if (self._inspector_sizes is not None
                    and isinstance(splitter, QSplitter)
                    and splitter.indexOf(inspector) >= 0
                    and len(self._inspector_sizes) == splitter.count()):
                splitter.setSizes(self._inspector_sizes)
            self._inspector_sizes = None
        else:
            if (isinstance(splitter, QSplitter)
                    and splitter.indexOf(inspector) >= 0):
                self._inspector_sizes = list(splitter.sizes())
            inspector.hide()

    # ---- filter wrap ----------------------------------------------------------
    @staticmethod
    def _find_filter_row(panel):
        lay = panel.layout()
        if lay is None:
            return None
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if isinstance(item, QHBoxLayout) and item.indexOf(panel.search) >= 0:
                return item
        return None

    def _wrap_filters(self) -> None:
        if self._filter_state is not None:
            return
        panel = self.window.library_panel
        frow = self._find_filter_row(panel)
        if frow is None:
            return
        # Snapshot the whole row BEFORE moving anything so the original
        # widget order can be rebuilt exactly on restore.
        snapshot = [frow.itemAt(i).widget() for i in range(frow.count())]
        movable = {getattr(panel, name) for name in self.FILTER_WIDGETS
                   if getattr(panel, name, None) is not None}
        labels = {getattr(panel, name): self.FILTER_LABELS[name]
                  for name in self.FILTER_WIDGETS
                  if getattr(panel, name, None) is not None}

        menu = QMenu(self.window)
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(6, 6, 6, 6)
        for w in snapshot:
            if w in movable:
                form.addRow(labels.get(w, ''), w)
        # PySide6 QMenu has no addWidget(); embed the form via QWidgetAction.
        item = QWidgetAction(self.window)
        item.setDefaultWidget(container)
        menu.addAction(item)

        btn = QToolButton()
        btn.setText('Filters ▾')
        btn.setToolTip('Secondary filters (SR / Ch / Tags / Flat)')
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(menu)
        frow.addWidget(btn)

        self._filter_state = (snapshot, menu, btn)

    def _unwrap_filters(self) -> None:
        if self._filter_state is None:
            return
        snapshot, menu, btn = self._filter_state
        panel = self.window.library_panel
        frow = self._find_filter_row(panel)
        if frow is not None:
            while frow.count():
                item = frow.takeAt(0)
                w = item.widget()
                if w is not None and w is not btn:
                    w.setParent(panel)
            for w in snapshot:
                frow.addWidget(w)
        btn.deleteLater()
        menu.deleteLater()
        self._filter_state = None

    # ---- accessors used by tests / callers -------------------------------------
    def filter_overflow(self):
        """The popup holding the secondary filters (None when not compact)."""
        if self._filter_state is None:
            return None
        return self._filter_state[1]