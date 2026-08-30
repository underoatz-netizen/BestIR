"""Summary tab: metric table A vs B with validity and main differences (WP-07)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

_FEATURE_ROWS = [
    ('transient', 'time_to_peak_ms', 'Time to peak (ms)'),
    ('transient', 'rise_time_ms', 'Rise time 10-90% (ms)'),
    ('transient', 'early_energy_5ms', 'Early energy 0-5 ms'),
    ('transient', 'early_late_ratio', 'Early/late ratio'),
    ('transient', 'centroid_ms', 'Energy centroid (ms)'),
    ('transient', 'crest_factor', 'Crest factor'),
    ('decay', 'd20_low_ms', 'Low-end D20 (ms)'),
    ('decay', 'boxiness_persistence_excess_db', 'Boxiness persistence (dB)'),
    ('decay', 'boxiness_ridge_hz', 'Boxiness ridge (Hz)'),
    ('phase', 'gd_median_ms', 'Group delay median (ms)'),
    ('phase', 'gd_spread_ms', 'Group delay spread (ms)'),
    ('phase', 'gd_valid_coverage', 'Valid phase coverage'),
]


class SummaryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Metric', 'A', 'B', 'Δ (A−B)'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 2)
        self.why = QTextEdit()
        self.why.setReadOnly(True)
        self.why.setPlaceholderText('Main reasons these IRs differ will appear here.')
        layout.addWidget(QLabel('Main differences:'), 0)
        layout.addWidget(self.why, 1)

    def show_fingerprints(self, fp_a, fp_b, name_a='A', name_b='B'):
        rows = []
        diffs = []
        for group, feat, label in _FEATURE_ROWS:
            fa = fp_a.all_features().get(feat) if fp_a else None
            fb = fp_b.all_features().get(feat) if fp_b else None
            va = fa.value if fa and fa.valid and fa.value is not None else None
            vb = fb.value if fb and fb.valid and fb.value is not None else None
            if va is None and vb is None:
                delta_text = 'n/a'
            elif va is None:
                delta_text = 'A invalid'
            elif vb is None:
                delta_text = 'B invalid'
            else:
                d = va - vb
                delta_text = f'{d:+.3f}'
                diffs.append((abs(d), label, d, va, vb))
            rows.append((label,
                         'n/a' if va is None else f'{va:.4g}',
                         'n/a' if vb is None else f'{vb:.4g}',
                         delta_text,
                         (fa.note if fa and not fa.valid else ''),
                         (fb.note if fb and not fb.valid else '')))
        self.table.setRowCount(len(rows))
        for i, (label, ta, tb, td, na, nb) in enumerate(rows):
            for j, text in enumerate((label, ta, tb, td)):
                item = QTableWidgetItem(text)
                if j > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, item)
            if na:
                self.table.item(i, 1).setToolTip(f'A: {na}')
            if nb:
                self.table.item(i, 2).setToolTip(f'B: {nb}')

        diffs.sort(reverse=True)
        lines = []
        for _, label, d, va, vb in diffs[:5]:
            direction = f'{name_a} higher' if d > 0 else f'{name_b} higher'
            lines.append(f'• {label}: {direction} by {abs(d):.3g} '
                         f'({va:.4g} vs {vb:.4g})')
        self.why.setPlainText('\n'.join(lines) or 'No measurable differences.')
