"""Response-aware search panel (WP-07): stage-2 ranking UI with explanations."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from app.extensions.advanced_matching import rank_by_response

PRESETS = {
    'Tight': ({'tone': 1.0, 'd20': 1.5},
              {'max_tone_db': 3.0}, {'d20': 25.0}),
    'Fast attack': ({'tone': 1.0, 'attack': 1.5},
                    {'max_tone_db': 3.0}, {'attack': 1.5}),
    'Low boxiness persistence': ({'tone': 1.0, 'boxiness': 1.5},
                                 {'max_tone_db': 3.0}, {'boxiness': 0.0}),
    'Smooth time response': ({'tone': 1.0, 'gd_spread': 1.5},
                             {'max_tone_db': 3.0}, {'gd_spread': 0.5}),
    'Custom': ({'tone': 1.0}, {}, {}),
}


class ResponseSearchPanel(QWidget):
    rank_requested = Signal(object)   # dict(request context)

    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout()
        self.preset_combo = QComboBox()
        for name in PRESETS:
            self.preset_combo.addItem(name)
        form.addRow('Preset', self.preset_combo)

        self.spin_tone = self._spin(0.0, 3.0, 0.1)
        self.spin_d20 = self._spin(0.0, 1.5, 0.1)
        self.spin_attack = self._spin(0.0, 1.5, 0.1)
        self.spin_boxiness = self._spin(0.0, 1.5, 0.1)
        self.spin_gd = self._spin(0.0, 1.5, 0.1)
        form.addRow('Weight: tone', self.spin_tone)
        form.addRow('Weight: low-end D20', self.spin_d20)
        form.addRow('Weight: fast attack', self.spin_attack)
        form.addRow('Weight: low boxiness', self.spin_boxiness)
        form.addRow('Weight: smooth GD', self.spin_gd)

        self.spin_max_tone = self._spin(0.5, 12.0, 0.5)
        self.spin_max_tone.setValue(3.0)
        form.addRow('Max tone error (dB)', self.spin_max_tone)

        self.policy_combo = QComboBox()
        self.policy_combo.addItems(['exclude', 'reject'])
        form.addRow('Missing-data policy', self.policy_combo)

        self.go_btn = QPushButton('Rank shortlist by response')
        self.go_btn.setDefault(True)
        form.addRow('', self.go_btn)

        self.result_list = QListWidget()
        self.explain = QTextEdit()
        self.explain.setReadOnly(True)
        self.explain.setMaximumHeight(130)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.result_list, 2)
        layout.addWidget(QLabel('Why this ranking:'), 0)
        layout.addWidget(self.explain, 1)

        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        self.go_btn.clicked.connect(self._emit)
        self.result_list.currentRowChanged.connect(self._show_explain)
        self._apply_preset('Tight')
        self._last = []

    @staticmethod
    def _spin(lo, hi, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSingleStep(step)
        return s

    def _apply_preset(self, name: str):
        weights, constraints, targets = PRESETS.get(name, PRESETS['Custom'])
        self.spin_tone.setValue(weights.get('tone', 1.0))
        self.spin_d20.setValue(weights.get('d20', 0.0))
        self.spin_attack.setValue(weights.get('attack', 0.0))
        self.spin_boxiness.setValue(weights.get('boxiness', 0.0))
        self.spin_gd.setValue(weights.get('gd_spread', 0.0))
        self.spin_max_tone.setValue(constraints.get('max_tone_db', 3.0))

    def _emit(self):
        self.rank_requested.emit({
            'weights': {'tone': self.spin_tone.value(),
                        'd20': self.spin_d20.value(),
                        'attack': self.spin_attack.value(),
                        'boxiness': self.spin_boxiness.value(),
                        'gd_spread': self.spin_gd.value()},
            'constraints': {'max_tone_db': self.spin_max_tone.value()},
            'policy': self.policy_combo.currentText(),
        })

    def show_results(self, ranked, name_by_path: dict | None = None):
        self._last = ranked
        self.result_list.clear()
        for c in ranked:
            name = c.record.path.replace('\\', '/').rsplit('/', 1)[-1]
            if c.excluded:
                self.result_list.addItem(f'✗ {name} — {c.reason}')
            else:
                self.result_list.addItem(
                    f'#{c.rank} {name} — score {c.breakdown.total:.3f}')
        self.explain.setPlainText(
            'Select a candidate to see its score breakdown.')

    def _show_explain(self, row: int):
        if 0 <= row < len(self._last):
            c = self._last[row]
            if c.breakdown is not None:
                self.explain.setPlainText(c.breakdown.explain())
            else:
                self.explain.setPlainText(c.reason or 'no breakdown')
