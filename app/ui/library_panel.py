"""Library panel: folders, filters and the record table."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QTableView,
                               QVBoxLayout, QWidget)

from app.core.analysis import AnalysisResult
from .model import COL, IRTableModel


class TagCombo(QComboBox):
    """Combo box with checkable tag entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModelColumn(0)
        self._view = self.view()
        self._view.clicked.connect(lambda i: self._toggle(i.row()))
        self.insertItem(0, 'Any tag')
        self._checked: set[str] = set()

    def _toggle(self, row: int) -> None:
        text = self.itemText(row)
        if row == 0:
            return
        if text in self._checked:
            self._checked.discard(text)
            self.setItemText(row, text)
        else:
            self._checked.add(text)
        self._update_label()

    def _update_label(self) -> None:
        if self._checked:
            self.setItemText(0, f'Tags: {len(self._checked)}')
        else:
            self.setItemText(0, 'Any tag')

    def tags(self) -> set[str]:
        return set(self._checked)

    def set_tags_available(self, tags: list[str]) -> None:
        keep = {t for t in self._checked if t in tags}
        self._checked = keep
        while self.count() > 1:
            self.removeItem(1)
        for t in sorted(tags):
            self.addItem(t)
        self._update_label()


class LibraryPanel(QWidget):
    filters_changed = Signal()
    selection_changed = Signal(list)          # list[AnalysisResult]
    folders_changed = Signal(list)            # list[str]
    rescan_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(560)

        # folders row
        top = QHBoxLayout()
        self.add_btn = QPushButton('Add Folder…')
        self.rescan_btn = QPushButton('Rescan (force)')
        top.addWidget(self.add_btn)
        top.addWidget(self.rescan_btn)
        top.addStretch(1)

        self.folder_list = QListWidget()
        self.folder_list.setMaximumHeight(70)
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.folder_list.model().rowsInserted.connect(self._emit_folders)
        self.folder_list.model().rowsRemoved.connect(self._emit_folders)

        # filter row
        frow = QHBoxLayout()
        frow.addWidget(QLabel('Search'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('substring in path…')
        frow.addWidget(self.search, 1)
        frow.addWidget(QLabel('SR'))
        self.sr_combo = QComboBox()
        self.sr_combo.addItems(['Any', '44100', '48000', '88200', '96000'])
        frow.addWidget(self.sr_combo)
        frow.addWidget(QLabel('Ch'))
        self.ch_combo = QComboBox()
        self.ch_combo.addItems(['Any', 'Mono', 'Stereo'])
        frow.addWidget(self.ch_combo)
        self.tag_combo = TagCombo()
        frow.addWidget(self.tag_combo)
        frow.addWidget(QLabel('Flat ≤'))
        self.flat_spin = QDoubleSpinBox()
        self.flat_spin.setRange(0.0, 20.0)
        self.flat_spin.setDecimals(1)
        self.flat_spin.setSpecialValueText('off')
        self.flat_spin.setValue(0.0)
        frow.addWidget(self.flat_spin)
        self.clear_btn = QPushButton('Clear')
        frow.addWidget(self.clear_btn)

        # table
        self.model = IRTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        hh = self.table.horizontalHeader()
        hh.resizeSection(COL['Name'], 250)
        hh.resizeSection(COL['Folder'], 110)
        for c in (COL['Score'], COL['SR'], COL['Ch'], COL['Len ms'],
                  COL['Flat'], COL['Tilt'], COL['Low'], COL['LowMid'],
                  COL['Mid'], COL['MidHigh'], COL['High'], COL['Air']):
            hh.resizeSection(c, 48)
        hh.setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.folder_list)
        layout.addLayout(frow)
        layout.addWidget(self.table, 1)

        self.add_btn.clicked.connect(self._add_folder)
        self.rescan_btn.clicked.connect(self.rescan_requested.emit)
        self.search.textChanged.connect(lambda _: self.filters_changed.emit())
        self.sr_combo.currentIndexChanged.connect(lambda _: self.filters_changed.emit())
        self.ch_combo.currentIndexChanged.connect(lambda _: self.filters_changed.emit())
        self.tag_combo.view().clicked.connect(lambda _: self.filters_changed.emit())
        self.tag_combo.view().pressed.connect(lambda _: self.filters_changed.emit())
        self.flat_spin.valueChanged.connect(lambda _: self.filters_changed.emit())
        self.clear_btn.clicked.connect(self._clear_filters)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        self.table.doubleClicked.connect(
            lambda i: self.selection_changed.emit([self.model.record_at(i.row())]))

    # ---- folders ---------------------------------------------------------------
    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, 'Add IR folder')
        if d and not self.folder_list.findItems(d, Qt.MatchExactly):
            self.folder_list.addItem(d)

    def folders(self) -> list[str]:
        return [self.folder_list.item(i).text()
                for i in range(self.folder_list.count())]

    def _emit_folders(self, *_) -> None:
        self.folders_changed.emit(self.folders())

    # ---- filters ------------------------------------------------------------------
    def filters(self) -> dict:
        return {
            'text': self.search.text().strip().lower(),
            'sr': 0 if self.sr_combo.currentIndex() == 0
                  else int(self.sr_combo.currentText()),
            'channels': self.ch_combo.currentIndex(),
            'tags': self.tag_combo.tags(),
            'max_flatness': None if self.flat_spin.value() == 0.0
                            else self.flat_spin.value(),
        }

    def _clear_filters(self) -> None:
        self.search.clear()
        self.sr_combo.setCurrentIndex(0)
        self.ch_combo.setCurrentIndex(0)
        self.flat_spin.setValue(0.0)
        self.tag_combo.set_tags_available(getattr(self, '_known_tags', []))
        self.filters_changed.emit()

    def set_available_tags(self, tags: list[str]) -> None:
        self._known_tags = sorted(tags)
        self.tag_combo.set_tags_available(self._known_tags)

    def apply_filters(self, library: list[AnalysisResult]) -> list[AnalysisResult]:
        f = self.filters()
        out = []
        for r in library:
            p = r.path.lower()
            if f['text'] and f['text'] not in p:
                continue
            if f['sr'] and r.sample_rate != f['sr']:
                continue
            if f['channels'] == 1 and r.channels != 1:
                continue
            if f['channels'] == 2 and r.channels != 2:
                continue
            if f['tags'] and not f['tags'].issubset(set(r.tags)):
                continue
            if f['max_flatness'] is not None and r.flatness_db > f['max_flatness']:
                continue
            out.append(r)
        return out

    # ---- selection ------------------------------------------------------------------
    def _on_selection(self, *_):
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        recs = [self.model.record_at(r) for r in sorted(rows)]
        self.selection_changed.emit([r for r in recs if r])

    def select_record(self, record: AnalysisResult) -> bool:
        for row, r in enumerate(self.model.records):
            if r.path == record.path:
                self.table.selectRow(row)
                self.table.scrollTo(self.model.index(row, 0))
                return True
        return False

    def selected_records(self) -> list[AnalysisResult]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.record_at(r) for r in rows if self.model.record_at(r)]

    def visible_records(self) -> list[AnalysisResult]:
        return list(self.model.records)
