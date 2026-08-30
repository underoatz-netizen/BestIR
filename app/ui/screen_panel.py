"""Screening panel: target-curve modes + ranking + export actions."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QListWidget, QPushButton, QSlider,
                               QTabWidget, QVBoxLayout, QWidget)

from app.core.analysis import BANDS, SCORE_HI, SCORE_LO, AnalysisResult
from app.core.presets import PRESETS, PRESET_DESCRIPTIONS


class ScreenPanel(QWidget):
    target_changed = Signal(object)      # np.ndarray | None
    rank_requested = Signal()
    clear_rank_requested = Signal()
    export_selected = Signal()
    export_topn = Signal(int)
    record_requested = Signal(float)     # seconds
    record_cancel = Signal()
    load_di_requested = Signal()
    di_cleared = Signal()
    match_wav_requested = Signal()

    TONE_MATCH_IDX = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reference_curve: np.ndarray | None = None
        self._reference_name: str | None = None
        self._di_curve: np.ndarray | None = None
        self._di_name: str | None = None
        self._custom_out_curve: np.ndarray | None = None
        self._recording = False

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_preset_tab(), 'Preset')
        self.tabs.addTab(self._make_bands_tab(), 'Bands')
        self.tabs.addTab(self._make_reference_tab(), 'Reference')
        self.tabs.addTab(self._make_tonematch_tab(), 'Tone Match')
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(self._emit_target)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel('Range'))
        self.range_combo = QComboBox()
        self.range_combo.addItem('Core 80–8k', SCORE_LO)
        self.range_combo.addItem('Full 20–20k', 20.0)
        bottom.addWidget(self.range_combo)
        bottom.addWidget(QLabel('Top'))
        self.topn_spin = QDoubleSpinBox()
        self.topn_spin.setRange(1, 200)
        self.topn_spin.setValue(25)
        self.topn_spin.setDecimals(0)
        bottom.addWidget(self.topn_spin)
        self.rank_btn = QPushButton('Rank')
        self.rank_btn.setDefault(True)
        self.clear_rank_btn = QPushButton('Clear rank')
        bottom.addWidget(self.rank_btn)
        bottom.addWidget(self.clear_rank_btn)
        bottom.addStretch(1)
        self.export_sel_btn = QPushButton('Export Selected')
        self.export_top_btn = QPushButton('Export Top-N')
        bottom.addWidget(self.export_sel_btn)
        bottom.addWidget(self.export_top_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)

        self.rank_btn.clicked.connect(self.rank_requested.emit)
        self.clear_rank_btn.clicked.connect(self.clear_rank_requested.emit)
        self.export_sel_btn.clicked.connect(self.export_selected.emit)
        self.export_top_btn.clicked.connect(
            lambda: self.export_topn.emit(int(self.topn_spin.value())))

    # ---- tabs ---------------------------------------------------------------
    def _make_preset_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self.preset_list = QListWidget()
        for name in PRESETS:
            self.preset_list.addItem(name)
        self.preset_list.setCurrentRow(-1)
        self.preset_list.itemClicked.connect(lambda _: self._emit_target())
        self.preset_list.currentItemChanged.connect(lambda *_: self._emit_target())
        lay.addWidget(self.preset_list, 1)
        self.preset_desc = QLabel('Pick a tonal preset, then press Rank.')
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setAlignment(Qt.AlignTop)
        lay.addWidget(self.preset_desc, 1)
        return w

    def _make_bands_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.band_sliders: dict[str, QSlider] = {}
        self.band_labels: dict[str, QLabel] = {}
        for name, lo, hi in BANDS:
            row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(-60, 60)
            slider.setValue(0)
            label = QLabel('0.0 dB')
            label.setMinimumWidth(52)
            slider.valueChanged.connect(
                lambda v, lb=label: (lb.setText(f'{v / 10:+.1f} dB'),
                                     self._emit_target()))
            row.addWidget(slider, 1)
            row.addWidget(label)
            container = QWidget()
            container.setLayout(row)
            form.addRow(f'{name} {lo:.0f}–{hi:.0f}', container)
            self.band_sliders[name] = slider
            self.band_labels[name] = label
        reset = QPushButton('Reset sliders')
        reset.clicked.connect(self._reset_bands)
        form.addRow('', reset)
        return w

    def _make_reference_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ref_label = QLabel('No reference set — select an IR and press '
                                '"Use as Reference" in the inspector.')
        self.ref_label.setWordWrap(True)
        lay.addWidget(self.ref_label)
        clear = QPushButton('Clear reference')
        clear.clicked.connect(self.clear_reference)
        lay.addWidget(clear)
        lay.addStretch(1)
        return w

    def _make_tonematch_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # DI capture row
        row = QHBoxLayout()
        self.record_btn = QPushButton('● Record DI')
        self.record_btn.setToolTip('Record a dry guitar riff from the default input')
        row.addWidget(self.record_btn)
        row.addWidget(QLabel('Length'))
        self.rec_seconds = QDoubleSpinBox()
        self.rec_seconds.setRange(5.0, 60.0)
        self.rec_seconds.setValue(15.0)
        self.rec_seconds.setDecimals(0)
        self.rec_seconds.setSuffix(' s')
        row.addWidget(self.rec_seconds)
        self.load_di_btn = QPushButton('Load DI WAV…')
        row.addWidget(self.load_di_btn)
        self.clear_di_btn = QPushButton('Clear DI')
        row.addWidget(self.clear_di_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.di_label = QLabel(
            'No DI yet. Record a 10–20 s dry riff (or load one) — it becomes the '
            'tone reference of your chain.')
        self.di_label.setWordWrap(True)
        lay.addWidget(self.di_label)

        # output target row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel('Wanted output tone'))
        self.out_combo = QComboBox()
        self.out_combo.addItem('Balanced (flat out)', 'Flat')
        for name in PRESETS:
            if name != 'Flat':
                self.out_combo.addItem(name, name)
        self.out_combo.addItem('Match WAV tone…', '__wav__')
        row2.addWidget(self.out_combo, 1)
        self.tm_rank_btn = QPushButton('⚔ Find Matching IRs')
        self.tm_rank_btn.setToolTip('Rank the library by how well each IR turns '
                                    'YOUR DI into the wanted output')
        self.tm_rank_btn.setDefault(True)
        row2.addWidget(self.tm_rank_btn)
        lay.addLayout(row2)

        self.tm_hint = QLabel(
            'Press "Find Matching IRs": the left table will show ONLY the best '
            'matches (Top-N). Plot colors: yellow = DI tone, orange dashes = IR '
            'you need, green = selected IR, blue = resulting output EQ. '
            '"Clear ranking" brings the full list back.')
        self.tm_hint.setWordWrap(True)
        self.tm_hint.setStyleSheet('color:#9aa4b0;')
        lay.addWidget(self.tm_hint)

        self.output_label = QLabel('')
        self.output_label.setStyleSheet('color:#4fc3f7;')
        lay.addWidget(self.output_label)
        lay.addStretch(1)

        self.record_btn.clicked.connect(self._on_record_btn)
        self.load_di_btn.clicked.connect(self.load_di_requested.emit)
        self.clear_di_btn.clicked.connect(self.clear_di)
        self.out_combo.currentIndexChanged.connect(self._on_out_combo)
        self.tm_rank_btn.clicked.connect(self.rank_requested.emit)
        return w

    def _on_record_btn(self):
        if self._recording:
            self.record_cancel.emit()
        else:
            self.record_requested.emit(float(self.rec_seconds.value()))

    def _on_out_combo(self, *_):
        if self.out_combo.currentData() == '__wav__' and self._custom_out_curve is None:
            self.match_wav_requested.emit()
        else:
            self._emit_target()

    # ---- DI state ---------------------------------------------------------------
    def is_tone_match_active(self) -> bool:
        return self.tabs.currentIndex() == self.TONE_MATCH_IDX

    def has_di(self) -> bool:
        return self._di_curve is not None

    def set_di(self, curve: np.ndarray, name: str, summary: str) -> None:
        self._di_curve = curve
        self._di_name = name
        self.di_label.setText(f'DI tone ref: {name}\n{summary}')
        if self.is_tone_match_active():
            self._emit_target()

    def clear_di(self) -> None:
        self._di_curve = None
        self._di_name = None
        self._custom_out_curve = None
        self.di_label.setText(
            'No DI yet. Record a 10–20 s dry riff (or load one) — it becomes the '
            'tone reference of your chain.')
        self.output_label.setText('')
        idx = self.out_combo.findData('__wav__')
        if idx >= 0:
            self.out_combo.removeItem(idx)
        self.di_cleared.emit()
        self._emit_target()

    def set_custom_output_curve(self, curve: np.ndarray, name: str) -> None:
        self._custom_out_curve = curve
        idx = self.out_combo.findData('__wav__')
        if idx < 0:
            self.out_combo.addItem(f'Match WAV: {name}', '__wav__')
        else:
            self.out_combo.setItemText(idx, f'Match WAV: {name}')
        self.out_combo.setCurrentIndex(idx)
        self._emit_target()

    def cancel_match_wav(self) -> None:
        idx = self.out_combo.findData('__wav__')
        if idx >= 0 and self.out_combo.currentIndex() == idx:
            self.out_combo.setCurrentIndex(0 if idx != 0 else 1)

    # ---- recording state ------------------------------------------------------------
    def begin_record(self) -> None:
        self._recording = True
        self.record_btn.setText('■ Stop')
        self.di_label.setText('Recording…')

    def update_record_progress(self, elapsed: float, total: float) -> None:
        self.di_label.setText(f'Recording… {elapsed:.1f} s / {total:.0f} s')

    def end_record(self) -> None:
        self._recording = False
        self.record_btn.setText('● Record DI')

    def set_output_summary(self, text: str) -> None:
        self.output_label.setText(text)

    # ---- target construction ---------------------------------------------------
    def current_target(self) -> np.ndarray | None:
        idx = self.tabs.currentIndex()
        if idx == 0:
            item = self.preset_list.currentItem()
            if item is None and self.preset_list.selectedItems():
                item = self.preset_list.selectedItems()[0]
            if item is None:
                return None
            from app.core.matching import target_from_band_offsets
            return target_from_band_offsets(PRESETS[item.text()])
        if idx == 1:
            from app.core.matching import target_from_band_offsets
            offsets = {name: s.value() / 10.0
                       for name, s in self.band_sliders.items()}
            return target_from_band_offsets(offsets)
        if idx == 2:
            return self._reference_curve
        if idx == self.TONE_MATCH_IDX:
            return self._needed_ir_curve()
        return None

    def _needed_ir_curve(self) -> np.ndarray | None:
        """IR curve required to map the DI onto the wanted output tone."""
        from app.core.tonematch import needed_ir_curve
        if self._di_curve is None:
            return None
        out_curve = self._output_target_curve()
        if out_curve is None:
            return None
        lo, hi = self.score_range()
        return needed_ir_curve(self._di_curve, out_curve, lo, hi)

    def _output_target_curve(self) -> np.ndarray | None:
        from app.core.matching import target_from_band_offsets
        data = self.out_combo.currentData()
        if data == '__wav__':
            return self._custom_out_curve
        return target_from_band_offsets(PRESETS.get(data, PRESETS['Flat']))

    def _emit_target(self, *_):
        if self.tabs.currentIndex() == 0:
            item = self.preset_list.currentItem()
            self.preset_desc.setText(
                PRESET_DESCRIPTIONS.get(item.text(), '') if item else
                'Pick a tonal preset, then press Rank.')
        self.target_changed.emit(self.current_target())

    # ---- external setters ----------------------------------------------------------
    def set_reference(self, record: AnalysisResult) -> None:
        self._reference_curve = record.curve_db
        self._reference_name = record.path
        name = record.path.replace('\\', '/').rsplit('/', 1)[-1]
        self.ref_label.setText(f'Reference: {name}')
        self.tabs.setCurrentIndex(2)
        self._emit_target()

    def clear_reference(self) -> None:
        self._reference_curve = None
        self._reference_name = None
        self.ref_label.setText('No reference set — select an IR and press '
                               '"Use as Reference" in the inspector.')
        self._emit_target()

    def _reset_bands(self) -> None:
        for s in self.band_sliders.values():
            s.setValue(0)

    def score_range(self) -> tuple[float, float]:
        lo = self.range_combo.currentData()
        return (SCORE_LO, SCORE_HI) if lo == SCORE_LO else (20.0, 20000.0)

