"""Response-aware search panel (WP-07): stage-2 ranking UI with explanations.

U07: Simple mode presents the desired response (targets) + tone tolerance
first; Advanced mode exposes raw weights and the missing-metric policy. The
public B08/B16 payload (`get_preset_state` / `apply_preset_state` / the
`rank_requested` request) keeps its shape in both modes, and candidates carry
accessible Set A / Set B / Audition / Compare action buttons with dedicated
signals so the workbench can wire real handlers without parsing list text.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QTextEdit, QVBoxLayout, QWidget)

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

MODES = ('Simple', 'Advanced')

#: response dimension -> weight spinbox attribute (Simple edits activate it)
_TARGET_WEIGHT = {'d20': 'spin_d20', 'attack': 'spin_attack',
                  'boxiness': 'spin_boxiness', 'gd_spread': 'spin_gd'}
#: response dimension -> target spinbox range (ms / dB / ms)
_TARGET_RANGES = {'d20': (0.0, 100.0), 'attack': (0.0, 10.0),
                  'boxiness': (0.0, 10.0), 'gd_spread': (0.0, 10.0)}
_TARGET_LABELS = {'d20': 'Low-end D20 target (ms)',
                  'attack': 'Fast attack target (ms)',
                  'boxiness': 'Boxiness target (dB)',
                  'gd_spread': 'Group-delay spread target (ms)'}

_ACTION_BTN_QSS = f"""
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_CARD};
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 7.5pt;
    font-weight: 500;
}}
QPushButton:hover {{
    border-color: {ACCENT_GOLD};
    color: {ACCENT_GOLD};
}}
QPushButton:focus {{
    border: 1px solid {ACCENT_GOLD};
}}
"""


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


class _CandidateRow(QWidget):
    """One result-list row: rank/name plus accessible candidate actions (U07).

    Each action button carries an accessible name that identifies the
    candidate, and a single ``action`` callback re-emits through the panel's
    public signals.
    """

    def __init__(self, text: str, accessible_name: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 6, 2)
        lay.setSpacing(4)
        self.info_lbl = QLabel(text)
        self.info_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; background: transparent; border: none; "
            f"font-family: {FONT_FAMILY_MONO}; font-size: 8.5pt;")
        lay.addWidget(self.info_lbl, 1)

        self._buttons: dict[str, QPushButton] = {}
        for action, label in (('set_a', 'Set A'), ('set_b', 'Set B'),
                              ('audition', 'Audition'), ('compare', 'Compare')):
            btn = QPushButton(label)
            btn.setAccessibleName(f'{label}: {accessible_name}')
            btn.setStyleSheet(_ACTION_BTN_QSS)
            lay.addWidget(btn, 0)
            self._buttons[action] = btn

    def connect_action(self, callback):
        for action, btn in self._buttons.items():
            btn.clicked.connect(
                lambda _checked=False, a=action: callback(a))

    def action_button(self, action: str) -> QPushButton:
        return self._buttons[action]


class ResponseSearchPanel(QWidget):
    rank_requested = Signal(object)   # dict(request context)

    # U07: candidate-level actions, emitted with the RankedCandidate object.
    candidate_set_a = Signal(object)
    candidate_set_b = Signal(object)
    candidate_audition = Signal(object)
    candidate_compare = Signal(object)

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
            btn.setAccessibleName(f'Preset: {name}')
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
                QPushButton:focus {{
                    border: 1px solid {ACCENT_GOLD};
                }}
            """)
            btn.clicked.connect(lambda _, n=name: self._apply_preset(n))
            p_row.addWidget(btn)
            self._preset_btns[name] = btn
        p_row.addStretch(1)
        c_lay.addLayout(p_row)

        # Mode selector + tone anchor (U07: desired outcome before weights)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('Mode:'))
        self.mode_combo = QComboBox()
        for mode in MODES:
            self.mode_combo.addItem(mode)
        self.mode_combo.setAccessibleName('Search mode')
        mode_row.addWidget(self.mode_combo)
        self.anchor_lbl = QLabel('Tone anchor: library default')
        self.anchor_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8pt; "
            f"font-family: {FONT_FAMILY_MONO};")
        mode_row.addWidget(self.anchor_lbl, 1)
        c_lay.addLayout(mode_row)

        # Simple group: desired response targets (drives ranking directly)
        self.simple_group = QFrame()
        self.simple_group.setStyleSheet("QFrame { border: none; }")
        s_lay = QVBoxLayout(self.simple_group)
        s_lay.setContentsMargins(0, 2, 0, 2)
        s_lay.setSpacing(4)
        s_lbl = QLabel('Desired Response:')
        s_lbl.setStyleSheet(
            f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        s_lay.addWidget(s_lbl)

        s_grid = QHBoxLayout()
        s_cols = [[], []]
        self._target_spins: dict[str, QDoubleSpinBox] = {}
        for idx, key in enumerate(('d20', 'attack', 'boxiness', 'gd_spread')):
            lo, hi = _TARGET_RANGES[key]
            spin = self._spin(lo, hi, 0.1)
            spin.setAccessibleName(_TARGET_LABELS[key])
            self._target_spins[key] = spin
            spin.valueChanged.connect(
                lambda _v, k=key, s=spin: self._on_target_edited(k, s))
            col = QVBoxLayout()
            col.addWidget(QLabel(_TARGET_LABELS[key]))
            col.addWidget(spin)
            s_cols[idx // 2].append(col)
        for i, col_layout in enumerate(s_cols):
            box = QVBoxLayout()
            for lay in col_layout:
                box.addLayout(lay)
            s_grid.addLayout(box)
        s_lay.addLayout(s_grid)
        # ``simple_group`` must belong to the control card.  Leaving this
        # frame out of the layout makes Qt treat it as a top-level window,
        # producing a new "Desired Response" popup whenever Compare opens.
        c_lay.addWidget(self.simple_group)

        # Shared tone tolerance row (label follows the mode)
        tol_row = QHBoxLayout()
        self.max_tone_lbl = QLabel('Tone tolerance (dB):')
        self.max_tone_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-weight: 600; font-size: 8.5pt;")
        tol_row.addWidget(self.max_tone_lbl)
        self.spin_max_tone = self._spin(0.5, 12.0, 0.5)
        self.spin_max_tone.setValue(3.0)
        tol_row.addWidget(self.spin_max_tone, 0)
        tol_row.addStretch(1)
        c_lay.addLayout(tol_row)
        self._tolerance_row = tol_row

        # Advanced group: raw weights + missing-metric policy
        self.advanced_group = QFrame()
        self.advanced_group.setStyleSheet("QFrame { border: none; }")
        a_lay = QVBoxLayout(self.advanced_group)
        a_lay.setContentsMargins(0, 2, 0, 2)
        a_lay.setSpacing(4)
        a_lbl = QLabel('Weights & Policy:')
        a_lbl.setStyleSheet(
            f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        a_lay.addWidget(a_lbl)

        w_grid = QHBoxLayout()
        w1 = QVBoxLayout()
        w1.addWidget(QLabel('Tone Weight:'))
        self.spin_tone = self._spin(0.0, 3.0, 0.1)
        w1.addWidget(self.spin_tone)
        w1.addWidget(QLabel('Low-end D20 Weight:'))
        self.spin_d20 = self._spin(0.0, 1.5, 0.1)
        w1.addWidget(self.spin_d20)
        w1.addWidget(QLabel('Fast Attack Weight:'))
        self.spin_attack = self._spin(0.0, 1.5, 0.1)
        w1.addWidget(self.spin_attack)
        w_grid.addLayout(w1)

        w2 = QVBoxLayout()
        w2.addWidget(QLabel('Anti-Boxiness Weight:'))
        self.spin_boxiness = self._spin(0.0, 1.5, 0.1)
        w2.addWidget(self.spin_boxiness)
        w2.addWidget(QLabel('Smooth Group Delay:'))
        self.spin_gd = self._spin(0.0, 1.5, 0.1)
        w2.addWidget(self.spin_gd)
        w2.addWidget(QLabel('Missing Metric Policy:'))
        self.policy_combo = QComboBox()
        self.policy_combo.addItems(['exclude', 'reject'])
        self.policy_combo.setAccessibleName('Missing metric policy')
        w2.addWidget(self.policy_combo)
        w_grid.addLayout(w2)
        a_lay.addLayout(w_grid)
        c_lay.addWidget(self.advanced_group)

        # Go button
        action_row = QHBoxLayout()
        self.go_btn = QPushButton('⚡ Rank Shortlist by Response')
        self.go_btn.setObjectName('primaryGoldBtn')
        self.go_btn.setAccessibleName('Rank shortlist by response')
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
            QPushButton:focus {{
                border: 2px solid #ffffff;
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
                padding: 4px 4px;
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

        # Legacy hidden preset combo kept for compatibility (B08 tests rely on
        # the public preset buttons, but external callers may read this).
        self.preset_combo = QComboBox()
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.setVisible(False)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)

        self.mode_combo.currentTextChanged.connect(self._set_mode)
        self.go_btn.clicked.connect(self._emit)
        self.result_list.currentRowChanged.connect(self._show_explain)
        self._targets: dict = {}
        self._apply_preset('Tight Low')
        self._last = []
        self.set_tone_anchor(None)
        self._set_mode('Simple')

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
            QDoubleSpinBox:focus {{
                border: 1px solid {ACCENT_GOLD};
            }}
        """)
        return s

    # ---- U07: mode presentation -------------------------------------------
    def _set_mode(self, mode: str):
        simple = mode == 'Simple'
        self.simple_group.setVisible(simple)
        self.advanced_group.setVisible(not simple)
        self.max_tone_lbl.setText('Tone tolerance (dB):' if simple
                                  else 'Max tone error (dB):')

    def current_mode(self) -> str:
        return self.mode_combo.currentText()

    def set_tone_anchor(self, name: str | None):
        """Show which IR drives the stage-1 tone shortlist (U07)."""
        self._anchor = name
        if name:
            short = name.replace('\\', '/').rsplit('/', 1)[-1]
            self.anchor_lbl.setText(f'Tone anchor: {short}')
            self.anchor_lbl.setToolTip(name)
        else:
            self.anchor_lbl.setText('Tone anchor: library default')
            self.anchor_lbl.setToolTip('')

    # ---- presets / state (B08) --------------------------------------------
    def _apply_preset(self, name: str):
        self.apply_preset_state(preset_state(name))

    def get_preset_state(self) -> dict:
        """Plain-data snapshot of the current request spec (B08).

        Includes response `targets` so a saved preset round-trips without
        dropping them. JSON-serializable; safe to persist externally. The
        payload shape is identical in Simple and Advanced mode.
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
        means "no response targets" (e.g. the Custom preset). Weight spinboxes
        are restored first and the target spinboxes are filled with signals
        blocked so restoring a snapshot never auto-activates zero weights.
        """
        weights = state.get('weights') or {}
        constraints = state.get('constraints') or {}
        self.spin_tone.setValue(weights.get('tone', 1.0))
        self.spin_d20.setValue(weights.get('d20', 0.0))
        self.spin_attack.setValue(weights.get('attack', 0.0))
        self.spin_boxiness.setValue(weights.get('boxiness', 0.0))
        self.spin_gd.setValue(weights.get('gd_spread', 0.0))
        self.spin_max_tone.setValue(constraints.get('max_tone_db', 3.0))
        targets = dict(state.get('targets') or {})
        for key, spin in self._target_spins.items():
            spin.blockSignals(True)
            spin.setValue(targets.get(key, 0.0))
            spin.blockSignals(False)
        self._targets = targets
        policy = state.get('policy')
        if policy in ('exclude', 'reject'):
            self.policy_combo.setCurrentText(policy)
        name = state.get('name')
        if name and self.preset_combo.currentText() != name:
            # avoid the currentTextChanged handler clobbering restored targets
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText(name)
            self.preset_combo.blockSignals(False)

    # ---- Simple-mode target editing (U07) ----------------------------------
    def _on_target_edited(self, key: str, spin: QDoubleSpinBox):
        self._targets[key] = spin.value()
        weight = getattr(self, _TARGET_WEIGHT[key])
        if weight.value() == 0.0:
            weight.setValue(1.0)   # desired outcome drives ranking

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
            if name_by_path:
                name = name_by_path.get(c.record.path, name)
            if c.excluded:
                text = f'[X] {name}  -  Excluded: {c.reason}'
            else:
                text = f'#{c.rank} {name}  -  Score: {c.breakdown.total:.3f}'
            row = _CandidateRow(text, name)
            row.connect_action(
                lambda action, cand=c: self._candidate_action(cand, action))
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.result_list.addItem(item)
            self.result_list.setItemWidget(item, row)
        self.explain.setPlainText(
            'Select a candidate to see its detailed score breakdown.')

    def _candidate_action(self, candidate, action: str):
        if action == 'set_a':
            self.candidate_set_a.emit(candidate)
        elif action == 'set_b':
            self.candidate_set_b.emit(candidate)
        elif action == 'audition':
            self.candidate_audition.emit(candidate)
        elif action == 'compare':
            self.candidate_compare.emit(candidate)

    def _show_explain(self, row: int):
        if 0 <= row < len(self._last):
            c = self._last[row]
            if c.breakdown is not None:
                self.explain.setPlainText(c.breakdown.explain())
            else:
                self.explain.setPlainText(c.reason or 'no breakdown')
