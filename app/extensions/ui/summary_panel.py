"""Summary tab: metric table A vs B with validity and main differences (WP-07).

Enhanced with Boro UI design tokens and tactile metric cards.
U08: differences are ranked by a dimensionless normalized effect (never by
raw unit sizes across ms/dB/Hz/%), n/a cells show their reason inline, and
the prose describes which measurement is higher without claiming the higher
value sounds better.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QScrollArea, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from .metric_format import (format_cell, format_number, to_display_value,
                            unit_suffix)
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

#: per-feature acoustic reference scale so mixed-unit deltas (ms, dB, Hz, %)
#: rank on one dimensionless axis (U08) — same philosophy as the matching
#: scales in advanced_matching, kept local and display-only.
_EFFECT_SCALE = {
    'time_to_peak_ms': 2.0,
    'rise_time_ms': 2.0,
    'early_energy_5ms': 0.2,
    'early_late_ratio': 1.0,
    'centroid_ms': 5.0,
    'crest_factor': 6.0,          # dB display scale
    'd20_low_ms': 40.0,
    'boxiness_persistence_excess_db': 6.0,
    'boxiness_ridge_hz': 200.0,
    'gd_median_ms': 2.0,
    'gd_spread_ms': 2.0,
    'gd_valid_coverage': 20.0,    # percentage points
}


def normalized_effect(feature: str, delta: float, val_a: float | None,
                      val_b: float | None) -> float:
    """Dimensionless effect magnitude |delta| / reference scale (U08).

    Unknown features fall back to the relative change against the larger
    display value so the sort never compares raw unit sizes.
    """
    scale = _EFFECT_SCALE.get(feature)
    if scale is None:
        ref = max(abs(val_a or 0.0), abs(val_b or 0.0), 1e-9)
        scale = ref
    return abs(delta) / max(scale, 1e-9)


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
            card = MetricCard(title, unit=unit, feature=feat)
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
            QTextEdit:focus {{
                border: 1px solid {ACCENT_GOLD};
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
            na = fa.note if fa and not fa.valid else ''
            nb = fb.note if fb and not fb.valid else ''
            # display-only unit conversion; raw cached values are never altered
            da = to_display_value(feat, va, unit)
            db = to_display_value(feat, vb, unit)
            # U08: invalid cells show their reason inline, not only in tooltips
            ta = 'n/a' if da is None else format_cell(da, unit)
            if da is None and na:
                ta = f'n/a ({na})'
            tb = 'n/a' if db is None else format_cell(db, unit)
            if db is None and nb:
                tb = f'n/a ({nb})'
            if va is None and vb is None:
                delta_text = 'n/a'
            elif va is None:
                delta_text = f'A invalid ({na})' if na else 'A invalid'
            elif vb is None:
                delta_text = f'B invalid ({nb})' if nb else 'B invalid'
            elif da is None or db is None:
                delta_text = 'n/a'   # valid raw but not representable in unit
            else:
                d = da - db
                delta_text = format_cell(d, unit, signed=True, sig=3)
                # U08: dimensionless effect, never raw cross-unit magnitudes
                diffs.append((normalized_effect(feat, d, da, db),
                              label, d, da, db, unit))
            rows.append((label, ta, tb, delta_text, na, nb))
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

        # Format Difference Explanation (neutral, dimensionless ranking)
        diffs.sort(reverse=True)
        lines = []
        for _effect, label, d, da, db, unit in diffs[:6]:
            u_str = unit_suffix(unit)
            higher = name_a if d > 0 else name_b
            # U08: describe the measurement only — no "winner"/"better"
            lines.append(
                f'• {label}: {higher} is higher by '
                f'{format_number(abs(d), unit, sig=3)}{u_str} '
                f'({name_a}: {format_number(da, unit)} vs '
                f'{name_b}: {format_number(db, unit)})')
        body = '\n'.join(lines)
        if body:
            self.why.setPlainText(
                'Ranked by normalized effect; a higher value is a '
                'measurement, not a tone-quality judgement.\n\n' + body)
        else:
            self.why.setPlainText('No measurable acoustic differences.')
