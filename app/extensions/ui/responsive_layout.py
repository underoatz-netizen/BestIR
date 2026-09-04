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

Wave 7 / U02 adds the wide-mode counterpart: Search gets its own row with an
instance-local minimum usable width (>= 160 px) and the secondary filters
live in a separate collapsible row inside the panel. The compact overflow
popup is unchanged; entering compact first restores the original single-row
layout so the snapshot/restore path keeps its exact behavior.

All behaviors are opt-in via ExtendedMainWindow and are instance-local:
no legacy module globals, layouts or widgets are modified at source level.
"""
from __future__ import annotations

from PySide6.QtCore import (QEvent, QObject, QPoint, QRect, QSize, Qt)
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QLayout,
                               QMenu, QSplitter, QToolBar, QToolButton,
                               QWidget, QWidgetAction)


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
    """Responsive wrapping for the extended legacy window (U01 foundation,
    U02 wide search/filter rows).

    Attach to an ExtendedMainWindow; the adapter owns the extension toolbar
    (actions in a wrapping flow container) and watches window width to:

    * collapse the inspector into a drawer below ``responsive_width``,
    * move the secondary library filters into an overflow popup below it,
    * in wide mode, split the filter row into a dedicated Search row (with an
      instance-local minimum usable width) plus a collapsible secondary
      filter row (U02),
    * let the action flow wrap to extra rows as the toolbar narrows.
    """

    RESPONSIVE_WIDTH = 1280
    # U02: minimum usable width for the search field in wide mode (px).
    SEARCH_MIN_WIDTH = 160
    # U02: controls in the search row must remain touch/click usable even
    # when the surrounding legacy panel is compressed.
    SEARCH_ROW_MIN_HEIGHT = 33

    # LibraryPanel attribute -> popup row label for the movable filters.
    FILTER_WIDGETS = ('sr_combo', 'ch_combo', 'tag_combo', 'flat_spin')
    FILTER_LABELS = {'sr_combo': 'SR', 'ch_combo': 'Ch',
                     'tag_combo': 'Tags', 'flat_spin': 'Flat ≤'}

    def __init__(self, window, actions=(), responsive_width: int = RESPONSIVE_WIDTH):
        super().__init__(window)
        self.window = window
        self.responsive_width = int(responsive_width)
        # None until the first _apply_mode so the initial (wide) layout is
        # applied at construction time.
        self._compact: bool | None = None
        self._inspector_open = True
        self._inspector_sizes: list[int] | None = None
        self._filter_state = None  # (snapshot, menu, btn, action) while compact
        # The native menu/action is created once.  Recreating a QWidgetAction
        # while a previous popup is in deferred QObject teardown is unsafe on
        # Windows/PySide6; only its filter widgets move between layouts.
        self._overflow_popup = None  # (menu, action, container, form)
        # (snapshot, filter_layout, toggle, search_min_before, filter_widgets)
        # while the U02 wide split is active.
        self._wide_state = None
        self._filter_row_collapsed = False

        # These are instance-local overrides on the inherited widgets.  Keep
        # them across wide/compact transitions: the 33 px usability issue is
        # most apparent at compact widths, so restoring the legacy height on
        # entry to compact would defeat U02.
        panel = self.window.library_panel
        panel.search.setMinimumHeight(max(panel.search.minimumHeight(),
                                          self.SEARCH_ROW_MIN_HEIGHT))
        panel.clear_btn.setMinimumHeight(max(panel.clear_btn.minimumHeight(),
                                             self.SEARCH_ROW_MIN_HEIGHT))

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
            # Restore the original single-row layout first so the compact
            # overflow popup path keeps its exact (pre-U02) behavior.
            self._unwrap_wide_row()
            self._wrap_filters()
            self.set_inspector_open(False)
        else:
            self._unwrap_filters()
            self._wrap_wide_row()
            self.set_inspector_open(True)

    # ---- inspector drawer ----------------------------------------------------
    def is_compact(self) -> bool:
        return bool(self._compact)

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

        # The legacy labels are real widgets in the same layout, not metadata
        # on their controls.  Reparent them into the popup too; otherwise the
        # compact primary row displays orphaned "SR" / "Ch" / "Flat" labels.
        label_for = {}
        previous = None
        for w in snapshot:
            if w in movable:
                if isinstance(previous, QLabel):
                    label_for[w] = previous
            previous = w

        # Keep one menu/action for this adapter's lifetime.  QMenu owns the
        # native menu entry, so creating/deleting this QWidgetAction for every
        # resize can leave a deferred native teardown overlapping the next
        # addAction() on Windows.  The filter widgets themselves are still
        # reparented below as required by compact/wide mode.
        if self._overflow_popup is None:
            menu = QMenu(self.window)
            container = QWidget()
            form = QFormLayout(container)
            form.setContentsMargins(6, 6, 6, 6)
            popup_action = QWidgetAction(menu)
            popup_action.setDefaultWidget(container)
            menu.addAction(popup_action)
            self._overflow_popup = (menu, popup_action, container, form)
        else:
            menu, popup_action, container, form = self._overflow_popup

        btn = QToolButton()
        for w in snapshot:
            if w not in movable:
                continue
            label = label_for.get(w)
            if label is None:
                form.addRow(self.FILTER_LABELS.get(
                    next((name for name in self.FILTER_WIDGETS
                          if getattr(panel, name, None) is w), ''), ''), w)
            else:
                form.addRow(label, w)
        btn.setText('Filters ▾')
        btn.setToolTip('Secondary filters (SR / Ch / Tags / Flat)')
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(menu)
        frow.addWidget(btn)

        self._filter_state = (snapshot, menu, btn, popup_action)

    def _unwrap_filters(self) -> None:
        if self._filter_state is None:
            return
        snapshot, menu, btn, popup_action = self._filter_state
        panel = self.window.library_panel
        frow = self._find_filter_row(panel)
        if frow is not None:
            while frow.count():
                layout_item = frow.takeAt(0)
                w = layout_item.widget()
                if w is not None and w is not btn:
                    w.setParent(panel)
            for w in snapshot:
                frow.addWidget(w)
        # The menu/action remain alive for the adapter lifetime.  Only the
        # transient button is removed; this avoids QWidgetAction teardown
        # racing a subsequent compact transition.
        btn.setMenu(None)
        btn.deleteLater()
        self._filter_state = None

    # ---- U02: wide-mode search row + collapsible secondary filter row --------
    def _wrap_wide_row(self) -> None:
        """Split the legacy filter row (wide mode).

        Search + Clear keep the original row (which retains the layout's
        stretch slot) and the search field gets an instance-local minimum
        usable width; SR / Ch / Tags / Flat (with their leading labels) move
        to a new collapsible row inserted directly below. Every widget stays
        parented to the panel and no signal connections are touched.
        """
        if self._wide_state is not None:
            return
        panel = self.window.library_panel
        outer = panel.layout()
        frow = self._find_filter_row(panel)
        if outer is None or frow is None:
            return
        row_index = outer.indexOf(frow)
        snapshot = [frow.itemAt(i).widget() for i in range(frow.count())]
        snapshot = [w for w in snapshot if w is not None]
        movable = {getattr(panel, name) for name in self.FILTER_WIDGETS
                   if getattr(panel, name, None) is not None}
        # A QLabel belongs to the control that follows it; controls split into
        # the search row (kept) and the secondary filter row (moved).
        search_row: list[QWidget] = []
        filter_row: list[QWidget] = []
        pending: QWidget | None = None
        for w in snapshot:
            if isinstance(w, QLabel):
                pending = w
                continue
            group = filter_row if w in movable else search_row
            if pending is not None:
                group.append(pending)
                pending = None
            group.append(w)
        if pending is not None:
            filter_row.append(pending)

        while frow.count():
            item = frow.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(panel)
        for w in search_row:
            frow.addWidget(w)
        frow.setStretchFactor(panel.search, 1)
        search_min_before = panel.search.minimumWidth()
        panel.search.setMinimumWidth(max(search_min_before,
                                         self.SEARCH_MIN_WIDTH))

        toggle = QToolButton()
        toggle.setText('Filters ▾')
        toggle.setToolTip(
            'Show / hide secondary filters (SR / Ch / Tags / Flat)')
        toggle.setCheckable(True)
        toggle.toggled.connect(self.set_filter_row_collapsed)
        new_row = QHBoxLayout()
        outer.insertLayout(row_index + 1, new_row)
        new_row.addWidget(toggle)
        for w in filter_row:
            new_row.addWidget(w)
        new_row.addStretch(1)

        self._wide_state = (snapshot, new_row, toggle, search_min_before,
                            filter_row)

    def _unwrap_wide_row(self) -> None:
        """Restore the exact original single-row layout (pre-U02 order)."""
        if self._wide_state is None:
            return
        snapshot, new_row, toggle, search_min_before, filter_row = \
            self._wide_state
        panel = self.window.library_panel
        for w in filter_row:
            w.setVisible(True)
        self._filter_row_collapsed = False
        self._wide_state = None
        frow = self._find_filter_row(panel)
        while new_row.count():
            item = new_row.takeAt(0)
            w = item.widget()
            if w is not None and w is not toggle:
                w.setParent(panel)
        if frow is not None:
            while frow.count():
                item = frow.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(panel)
        panel.layout().removeItem(new_row)
        if frow is not None:
            for w in snapshot:
                frow.addWidget(w)
        panel.search.setMinimumWidth(search_min_before)
        toggle.setParent(None)
        toggle.deleteLater()

    def set_filter_row_collapsed(self, collapsed: bool) -> None:
        """Hide / show the secondary filter widgets (wide mode only)."""
        if self._wide_state is None:
            return
        collapsed = bool(collapsed)
        self._filter_row_collapsed = collapsed
        _, _, toggle, _, filter_row = self._wide_state
        for w in filter_row:
            w.setVisible(not collapsed)
        toggle.setText('Filters ▸' if collapsed else 'Filters ▾')
        toggle.blockSignals(True)
        toggle.setChecked(collapsed)
        toggle.blockSignals(False)

    def toggle_filter_row(self) -> None:
        self.set_filter_row_collapsed(not self._filter_row_collapsed)

    def filter_row_collapsed(self) -> bool:
        return self._filter_row_collapsed

    # ---- accessors used by tests / callers -------------------------------------
    def filter_overflow(self):
        """The popup holding the secondary filters (None when not compact)."""
        if self._filter_state is None:
            return None
        return self._filter_state[1]
