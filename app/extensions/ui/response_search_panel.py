"""Response-aware search panel (WP-07): stage-2 ranking UI with explanations.

Enhanced with Boro UI design tokens, tactile preset buttons, and score breakdown styling.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from app.extensions.advanced_matching import rank_by_response
from .styles_boro import (ACCENT_GOLD, ACCENT_GOLD_BG, BORDER_CARD,
                          COLOR_IR_A, COLOR_IR_B, FONT_FAMILY_MONO,
                          FONT_FAMILY_PRIMARY, SURFACE_CARD, SURFACE_RAISED,
                          TEXT_MAIN, TEXT_MUTED)

PRESETS = {
    'Tight Low': ({'tone': 1.0, 'd20': 1.5},
                  {'max_tone_db': 3.0}, {'d20': 25.0}),
    'Fast Attack': ({'tone': 1.0, 'attack': 1.5},
                    {'max_tone_db': 3.0}, {'attack': 1.5}),
    'Anti-Boxiness': ({'tone': 1.0, 'boxiness': 1.5},
                      {'max_tone_db': 3.0}, {'boxiness': 0.0}),
    'Smooth GD': ({'tone': 1.0, 'gd_spread': 1.5},
                  {'max_tone_db': 3.0}, {'gd_spread': 0.5}),
    'Custom': ({'tone': 1.0}, {}, {}),
}


def preset_state(name: str) -> dict:
    """Immutable plain-data snapshot of a named preset (B08).

    Kept JSON-serializable so presets can be saved/loaded without touching
    Qt state; `targets` are first-class members of the snapshot.
    """
    weights, constraints, targets = PRESETS.get(name, PRESETS['Custom'])
    return {'name': name,
            'weights': dict(weights),
            'constraints': dict(constraints),
            'targets': dict(targets)}


class ResponseSearchPanel(QWidget):
    rank_requested = Signal(object)   # dict(request context)

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # Top Control Card
        control_card = QFrame()
        control_card.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        c_lay = QVBoxLayout(control_card)
        c_lay.setContentsMargins(10, 8, 10, 8)
        c_lay.setSpacing(6)

        # Preset Buttons Row
        p_row = QHBoxLayout()
        p_lbl = QLabel('Presets:')
        p_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        p_row.addWidget(p_lbl)

        self._preset_btns = {}
        for name in PRESETS:
            btn = QPushButton(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {SURFACE_RAISED};
                    color: {TEXT_MAIN};
                    border: 1px solid {BORDER_CARD};
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 8pt;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    border-color: {ACCENT_GOLD};
                    color: {ACCENT_GOLD};
                }}
            """)
            btn.clicked.connect(lambda _, n=name: self._apply_preset(n))
            p_row.addWidget(btn)
            self._preset_btns[name] = btn
        p_row.addStretch(1)
        c_lay.addLayout(p_row)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(4)

        self.preset_combo = QComboBox()
        for name in PRESETS:
            self.preset_combo.addItem(name)
        # Keep preset_combo for compatibility
        self.preset_combo.setVisible(False)

        self.spin_tone = self._spin(0.0, 3.0, 0.1)
        self.spin_d20 = self._spin(0.0, 1.5, 0.1)
        self.spin_attack = self._spin(0.0, 1.5, 0.1)
        self.spin_boxiness = self._spin(0.0, 1.5, 0.1)
        self.spin_gd = self._spin(0.0, 1.5, 0.1)

        # 2-column form for weights
        w_grid = QHBoxLayout()
        w1 = QVBoxLayout()
        w1.addWidget(QLabel('Tone Weight:'))
        w1.addWidget(self.spin_tone)
        w1.addWidget(QLabel('Low-end D20 Weight:'))
        w1.addWidget(self.spin_d20)
        w1.addWidget(QLabel('Fast Attack Weight:'))
        w1.addWidget(self.spin_attack)
        w_grid.addLayout(w1)

        w2 = QVBoxLayout()
        w2.addWidget(QLabel('Anti-Boxiness Weight:'))
        w2.addWidget(self.spin_boxiness)
        w2.addWidget(QLabel('Smooth Group Delay:'))
        w2.addWidget(self.spin_gd)
        w2.addWidget(QLabel('Max Tone Error (dB):'))
        self.spin_max_tone = self._spin(0.5, 12.0, 0.5)
        self.spin_max_tone.setValue(3.0)
        w2.addWidget(self.spin_max_tone)
        w_grid.addLayout(w2)

        c_lay.addLayout(w_grid)

        # Missing policy & Go button
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel('Policy:'))
        self.policy_combo = QComboBox()
        self.policy_combo.addItems(['exclude', 'reject'])
        action_row.addWidget(self.policy_combo)

        self.go_btn = QPushButton('⚡ Rank Shortlist by Response')
        self.go_btn.setObjectName('primaryGoldBtn')
        self.go_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_GOLD};
                color: #000000;
                font-weight: bold;
                font-size: 9pt;
                padding: 6px 16px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #fed215;
            }}
        """)
        action_row.addWidget(self.go_btn, 1)
        c_lay.addLayout(action_row)

        main_layout.addWidget(control_card, 0)

        # Results & Explain
        self.result_list = QListWidget()
        self.result_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 4px;
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {ACCENT_GOLD_BG};
                color: {ACCENT_GOLD};
            }}
        """)

        self.explain = QTextEdit()
        self.explain.setReadOnly(True)
        self.explain.setMaximumHeight(120)
        self.explain.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
                padding: 6px 10px;
            }}
        """)

        main_layout.addWidget(self.result_list, 2)
        exp_lbl = QLabel('Score Breakdown & Explanation:')
        exp_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        main_layout.addWidget(exp_lbl, 0)
        main_layout.addWidget(self.explain, 1)

        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        self.go_btn.clicked.connect(self._emit)
        self.result_list.currentRowChanged.connect(self._show_explain)
        self._targets: dict = {}
        self._apply_preset('Tight Low')
        self._last = []

    @staticmethod
    def _spin(lo, hi, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSingleStep(step)
        s.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER_CARD};
                border-radius: 6px;
                padding: 4px 8px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
            }}
        """)
        return s

    def _apply_preset(self, name: str):
        self.apply_preset_state(preset_state(name))

    def get_preset_state(self) -> dict:
        """Plain-data snapshot of the current request spec (B08).

        Includes response `targets` so a saved preset round-trips without
        dropping them. JSON-serializable; safe to persist externally.
        """
        return {
            'name': self.preset_combo.currentText(),
            'weights': {'tone': self.spin_tone.value(),
                        'd20': self.spin_d20.value(),
                        'attack': self.spin_attack.value(),
                        'boxiness': self.spin_boxiness.value(),
                        'gd_spread': self.spin_gd.value()},
            'constraints': {'max_tone_db': self.spin_max_tone.value()},
            'targets': dict(self._targets),
            'policy': self.policy_combo.currentText(),
        }

    def apply_preset_state(self, state: dict):
        """Restore a snapshot produced by get_preset_state/preset_state.

        Targets survive the restore; an explicit missing/empty `targets`
        means "no response targets" (e.g. the Custom preset).
        """
        weights = state.get('weights') or {}
        constraints = state.get('constraints') or {}
        self.spin_tone.setValue(weights.get('tone', 1.0))
        self.spin_d20.setValue(weights.get('d20', 0.0))
        self.spin_attack.setValue(weights.get('attack', 0.0))
        self.spin_boxiness.setValue(weights.get('boxiness', 0.0))
        self.spin_gd.setValue(weights.get('gd_spread', 0.0))
        self.spin_max_tone.setValue(constraints.get('max_tone_db', 3.0))
        self._targets = dict(state.get('targets') or {})
        policy = state.get('policy')
        if policy in ('exclude', 'reject'):
            self.policy_combo.setCurrentText(policy)
        name = state.get('name')
        if name and self.preset_combo.currentText() != name:
            # avoid the currentTextChanged handler clobbering restored targets
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText(name)
            self.preset_combo.blockSignals(False)

    def _emit(self):
        self.rank_requested.emit({
            'weights': {'tone': self.spin_tone.value(),
                        'd20': self.spin_d20.value(),
                        'attack': self.spin_attack.value(),
                        'boxiness': self.spin_boxiness.value(),
                        'gd_spread': self.spin_gd.value()},
            'constraints': {'max_tone_db': self.spin_max_tone.value()},
            'targets': dict(self._targets),   # B08: forward preset targets
            'policy': self.policy_combo.currentText(),
        })

    def show_results(self, ranked, name_by_path: dict | None = None):
        self._last = ranked
        self.result_list.clear()
        for c in ranked:
            name = c.record.path.replace('\\', '/').rsplit('/', 1)[-1]
            if c.excluded:
                self.result_list.addItem(f'[X] {name:<30} - Excluded: {c.reason}')
            else:
                self.result_list.addItem(
                    f'#{c.rank:<2} {name:<30} - Score: {c.breakdown.total:.3f}')
        self.explain.setPlainText(
            'Select a candidate to see its detailed score breakdown.')

    def _show_explain(self, row: int):
        if 0 <= row < len(self._last):
            c = self._last[row]
            if c.breakdown is not None:
                self.explain.setPlainText(c.breakdown.explain())
            else:
                self.explain.setPlainText(c.reason or 'no breakdown')
