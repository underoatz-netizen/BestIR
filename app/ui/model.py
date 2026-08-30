"""Table model for the IR library."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from app.core.analysis import AnalysisResult

COLUMNS = ['Score', 'Name', 'Folder', 'SR', 'Ch', 'Len ms', 'Flat', 'Tilt',
           'Low', 'LowMid', 'Mid', 'MidHigh', 'High', 'Air', 'Tags']
COL = {name: i for i, name in enumerate(COLUMNS)}

_HEADER_TIPS = {
    'Score': 'RMS error (dB) between the IR curve and the active target over '
             'the scoring range (Core 80 Hz-8 kHz by default).\n'
             '0 = identical shape · under ~1: excellent · 1-3: close · '
             '3-6: noticeably different · over 6: far away.\n'
             'It compares tonal SHAPE only — overall level is normalized out '
             'and phase is ignored — so scores are comparable across '
             'libraries and sessions, not just within one ranking.',
    'Flat': 'Mean deviation from flat (dB) over 80 Hz-8 kHz. Lower = flatter.',
    'Tilt': 'Spectral slope (dB/octave, 200 Hz-8 kHz). Positive = brighter, '
            'negative = darker.',
    'Len ms': 'Audible length: onset to -60 dB decay.',
}
for _band in ('Low', 'LowMid', 'Mid', 'MidHigh', 'High', 'Air'):
    _HEADER_TIPS[_band] = ('Average level of this band relative to the '
                           'core-band mean (0 dB), in dB.')

_TOP5_BG = QColor(46, 84, 54)


class IRTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[AnalysisResult] = []
        self.top_n: int = 0  # how many leading rows are "rank winners"

    # ---- Qt plumbing -------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.records[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return self._text(r, col)
        if role == Qt.TextAlignmentRole:
            if col != COL['Name'] and col != COL['Tags'] and col != COL['Folder']:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole:
            if self.top_n and index.row() < self.top_n and r.score is not None:
                return _TOP5_BG
        if role == Qt.ToolTipRole:
            return r.path
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return COLUMNS[section]
        if role == Qt.ToolTipRole:
            return _HEADER_TIPS.get(COLUMNS[section])
        return None

    def sort(self, column, order):
        reverse = order == Qt.DescendingOrder

        def key(r: AnalysisResult):
            v = self._key(r, column)
            return (v is None, v)

        try:
            self.records.sort(key=key, reverse=reverse)
        except TypeError:
            return
        self.beginResetModel()
        self.endResetModel()

    # ---- content -----------------------------------------------------------
    def _key(self, r: AnalysisResult, column: int):
        if column == COL['Score']:
            return r.score
        if column == COL['Name']:
            return Path(r.path).name.lower()
        if column == COL['Folder']:
            return Path(r.path).parent.name.lower()
        if column == COL['SR']:
            return r.sample_rate
        if column == COL['Ch']:
            return r.channels
        if column == COL['Len ms']:
            return r.effective_length_ms
        if column == COL['Flat']:
            return r.flatness_db
        if column == COL['Tilt']:
            return r.tilt_db_oct
        if column == COL['Tags']:
            return ','.join(r.tags).lower()
        key = COLUMNS[column]
        return r.band_levels.get(key)

    def _text(self, r: AnalysisResult, column: int):
        if column == COL['Score']:
            return f'{r.score:.1f}' if r.score is not None else ''
        if column == COL['Name']:
            return Path(r.path).name
        if column == COL['Folder']:
            return Path(r.path).parent.name
        if column == COL['SR']:
            return str(r.sample_rate)
        if column == COL['Ch']:
            return 'M' if r.channels == 1 else 'S'
        if column == COL['Len ms']:
            return f'{r.effective_length_ms:.0f}'
        if column == COL['Flat']:
            return f'{r.flatness_db:.1f}'
        if column == COL['Tilt']:
            return f'{r.tilt_db_oct:+.1f}'
        if column == COL['Tags']:
            return ','.join(r.tags)
        key = COLUMNS[column]
        v = r.band_levels.get(key)
        return f'{v:+.1f}' if v is not None else ''

    def set_records(self, records: list[AnalysisResult], top_n: int = 0) -> None:
        self.beginResetModel()
        self.records = list(records)
        self.top_n = top_n
        self.endResetModel()

    def record_at(self, row: int) -> AnalysisResult | None:
        return self.records[row] if 0 <= row < len(self.records) else None
