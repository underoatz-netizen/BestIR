"""Summary tab: metric table A vs B with validity and main differences (WP-07).

Enhanced with Boro UI design tokens and tactile metric cards.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QScrollArea, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_IR_A, COLOR_IR_B,
                          FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY, SURFACE_CARD,
                          SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .widgets.metric_card import MetricCard

_FEATURE_ROWS = [
    ('transient', 'time_to_peak_ms', 'Time to peak (ms)', 'ms'),
    ('transient', 'rise_time_ms', 'Rise time 10-90% (ms)', 'ms'),
    ('transient', 'early_energy_5ms', 'Early energy 0-5 ms', ''),
    ('transient', 'early_late_ratio', 'Early/late ratio', ''),
    ('transient', 'centroid_ms', 'Energy centroid (ms)', 'ms'),
    ('transient', 'crest_factor', 'Crest factor', 'dB'),
    ('decay', 'd20_low_ms', 'Low-end D20 (ms)', 'ms'),
    ('decay', 'boxiness_persistence_excess_db', 'Boxiness persistence (dB)', 'dB'),
    ('decay', 'boxiness_ridge_hz', 'Boxiness ridge (Hz)', 'Hz'),
    ('phase', 'gd_median_ms', 'Group delay median (ms)', 'ms'),
    ('phase', 'gd_spread_ms', 'Group delay spread (ms)', 'ms'),
    ('phase', 'gd_valid_coverage', 'Valid phase coverage', '%'),
]

_TOP_CARDS = [
    ('Time to Peak', 'time_to_peak_ms', 'ms'),
    ('Early Energy (0-5ms)', 'early_energy_5ms', ''),
    ('Low-end D20', 'd20_low_ms', 'ms'),
    ('Boxiness Excess', 'boxiness_persistence_excess_db', 'dB'),
    ('Group Delay Median', 'gd_median_ms', 'ms'),
    ('Phase Coverage', 'gd_valid_coverage', '%'),
]


class SummaryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Top Grid: Key Metric Cards
        cards_box = QWidget()
        cards_grid = QGridLayout(cards_box)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(6)

        self._cards: dict[str, MetricCard] = {}
        for idx, (title, feat, unit) in enumerate(_TOP_CARDS):
            card = MetricCard(title, unit=unit)
            row, col = divmod(idx, 3)
            cards_grid.addWidget(card, row, col)
            self._cards[feat] = card

        layout.addWidget(cards_box, 0)

        # Splitter: Detailed Table (left) + Studio Differences (right)
        splitter = QSplitter(Qt.Horizontal)

        # Table container
        table_container = QWidget()
        tc_lay = QVBoxLayout(table_container)
        tc_lay.setContentsMargins(0, 0, 0, 0)
        tc_lay.setSpacing(4)
        tc_lbl = QLabel('Full Response Metrics:')
        tc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: 600; font-size: 8.5pt;")
        tc_lay.addWidget(tc_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Metric', 'IR A', 'IR B', 'Δ (A−B)'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.resizeSection(0, 190)
        hh.resizeSection(1, 80)
        hh.resizeSection(2, 80)
        tc_lay.addWidget(self.table, 1)
        splitter.addWidget(table_container)

        # Why differences container
        why_container = QWidget()
        wc_lay = QVBoxLayout(why_container)
        wc_lay.setContentsMargins(0, 0, 0, 0)
        wc_lay.setSpacing(4)
        wc_lbl = QLabel('Acoustic Differences Breakdown:')
        wc_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        wc_lay.addWidget(wc_lbl)

        self.why = QTextEdit()
        self.why.setReadOnly(True)
        self.why.setPlaceholderText('Key acoustic differences between IR A and IR B will appear here.')
        self.why.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 10px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_PRIMARY};
                font-size: 9.5pt;
                line-height: 1.5;
            }}
        """)
        wc_lay.addWidget(self.why, 1)
        splitter.addWidget(why_container)

        splitter.setSizes([500, 400])
        layout.addWidget(splitter, 1)

    def show_fingerprints(self, fp_a, fp_b, name_a='A', name_b='B'):
        # Update Metric Cards
        for feat, card in self._cards.items():
            fa = fp_a.all_features().get(feat) if fp_a else None
            fb = fp_b.all_features().get(feat) if fp_b else None
            va = fa.value if fa and fa.valid and fa.value is not None else None
            vb = fb.value if fb and fb.valid and fb.value is not None else None
            card.set_values(va, vb,
                            note_a=(fa.note if fa and not fa.valid else ''),
                            note_b=(fb.note if fb and not fb.valid else ''))

        # Update Full Table
        rows = []
        diffs = []
        for group, feat, label, unit in _FEATURE_ROWS:
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
                diffs.append((abs(d), label, d, va, vb, unit))
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

        # Format Difference Explanation
        diffs.sort(reverse=True)
        lines = []
        for _, label, d, va, vb, unit in diffs[:6]:
            u_str = f' {unit}' if unit else ''
            winner = name_a if d > 0 else name_b
            lines.append(f'• {label}: {winner} is higher by {abs(d):.3g}{u_str} ({va:.4g} vs {vb:.4g})')
        self.why.setPlainText('\n\n'.join(lines) or 'No measurable acoustic differences.')
