"""Inspector: full metrics, tags, mini waveform, audition controls."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSlider, QVBoxLayout,
                               QWidget)

from app.core.analysis import AnalysisResult
from app.core.audition import BUILTIN_SOURCES
from .styles import BORDER, SURFACE

_BAND_KEYS = ['Sub', 'Low', 'LowMid', 'Mid', 'MidHigh', 'High', 'Air']
_BAR_RANGE = (-12.0, 12.0)


class BandBar(QWidget):
    """Per-band level bars: one labelled progress row per band."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: dict[str, QProgressBar] = {}
        self._values: dict[str, QLabel] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(3)
        for row, name in enumerate(_BAND_KEYS):
            lbl = QLabel(name)
            lbl.setMinimumWidth(52)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(13)
            val = QLabel('—')
            val.setMinimumWidth(48)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(val, row, 2)
            self._bars[name] = bar
            self._values[name] = val
        grid.setColumnStretch(1, 1)

    def set_values(self, bands: dict[str, float]) -> None:
        for name in _BAND_KEYS:
            v = float(np.clip(bands.get(name, 0.0), *_BAR_RANGE))
            bar = self._bars[name]
            bar.setValue(int(round((v - _BAR_RANGE[0]) /
                                   (_BAR_RANGE[1] - _BAR_RANGE[0]) * 100)))
            bar.setStyleSheet(
                f'QProgressBar {{ border: 1px solid {BORDER}; border-radius: 3px; '
                f'background: {SURFACE}; }}'
                f'QProgressBar::chunk {{ background: '
                f'{"#4f9d69" if v >= 0 else "#b05050"}; border-radius: 2px; }}')
            self._values[name].setText(f'{bands.get(name, 0.0):+.1f} dB')


class InspectorPanel(QWidget):
    reference_requested = Signal(object)   # AnalysisResult
    play_requested = Signal()
    stop_requested = Signal()
    ab_step = Signal(int)                  # -1 / +1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)

        self.name_label = QLabel('No selection')
        self.name_label.setWordWrap(True)
        self.meta_label = QLabel('')

        form = QFormLayout()
        form.addRow(self.name_label)
        form.addRow(self.meta_label)

        self.bars = BandBar()
        self.metric_label = QLabel('')
        self.metric_label.setWordWrap(True)
        self.tag_label = QLabel('')
        self.tag_label.setStyleSheet('color:#8fd19e;')

        self.wave = pg.PlotWidget(background=SURFACE)
        self.wave.setFixedHeight(70)
        self.wave.setMouseEnabled(False, False)
        self.wave.hideAxis('bottom')
        self.wave.hideAxis('left')
        self.wave_item = pg.PlotCurveItem(fillLevel=0, brush='#3a6ea5', pen=None)
        self.wave.addItem(self.wave_item)

        # audition
        audition = QGroupBox('Audition')
        al = QVBoxLayout(audition)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel('Source'))
        self.source_combo = QComboBox()
        self.source_combo.addItems(list(BUILTIN_SOURCES) + ['Custom WAV'])
        src_row.addWidget(self.source_combo, 1)
        self.load_wav_btn = QPushButton('Load…')
        src_row.addWidget(self.load_wav_btn)
        al.addLayout(src_row)
        opt_row = QHBoxLayout()
        self.level_match = QCheckBox('Level match')
        self.level_match.setChecked(True)
        self.loop_check = QCheckBox('Loop')
        self.loop_check.setChecked(True)
        opt_row.addWidget(self.level_match)
        opt_row.addWidget(self.loop_check)
        opt_row.addStretch(1)
        al.addLayout(opt_row)
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel('Vol'))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 150)
        self.volume.setValue(100)
        vol_row.addWidget(self.volume, 1)
        al.addLayout(vol_row)
        btn_row = QHBoxLayout()
        self.play_btn = QPushButton('Play')
        self.stop_btn = QPushButton('Stop')
        self.prev_btn = QPushButton('◀ A/B')
        self.next_btn = QPushButton('A/B ▶')
        for b in (self.play_btn, self.stop_btn, self.prev_btn, self.next_btn):
            btn_row.addWidget(b)
        al.addLayout(btn_row)
        self.status_label = QLabel('')
        al.addWidget(self.status_label)

        ref_btn = QPushButton('Use as Reference')
        self.ref_row = QHBoxLayout()
        self.ref_row.addWidget(ref_btn)
        self.ref_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(form)
        layout.addWidget(self.bars)
        layout.addWidget(self.metric_label)
        layout.addWidget(self.tag_label)
        layout.addWidget(self.wave)
        layout.addWidget(audition)
        layout.addLayout(self.ref_row)
        layout.addStretch(1)

        ref_btn.clicked.connect(self._emit_reference)
        self.load_wav_btn.clicked.connect(self._load_wav)
        self.play_btn.clicked.connect(self.play_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.prev_btn.clicked.connect(lambda: self.ab_step.emit(-1))
        self.next_btn.clicked.connect(lambda: self.ab_step.emit(+1))
        self._current: AnalysisResult | None = None
        self._engine = None
        self._custom_request: tuple | None = None

    # ------------------------------------------------------------------
    def _emit_reference(self):
        if self._current:
            self.reference_requested.emit(self._current)

    def _load_wav(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load dry test WAV', '', 'Audio (*.wav *.flac *.aiff)')
        if not path:
            return
        from app.core.audio_io import load_ir
        data, sr = load_ir(path)
        self._custom_request = (data, sr)
        self._on_source_changed(self.source_combo.currentIndex())
        self.source_combo.setCurrentIndex(self.source_combo.count() - 1)
        self.status_label.setText(f'Loaded {path.replace(chr(92), "/").rsplit("/", 1)[-1]}')

    def set_engine(self, engine) -> None:
        self._engine = engine
        if not engine.available:
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.status_label.setText('No audio output device found.')
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

    def set_di_available(self, available: bool) -> None:
        """Show/hide the 'Recorded DI' audition source."""
        combo = self.source_combo
        idx = combo.findText('Recorded DI')
        if available and idx < 0:
            combo.insertItem(len(BUILTIN_SOURCES), 'Recorded DI')
        elif not available and idx >= 0:
            if combo.currentIndex() == idx:
                combo.setCurrentIndex(0)
            combo.removeItem(idx)

    def _on_source_changed(self, idx: int):
        if self.source_combo.currentText() == 'Custom WAV' and \
                hasattr(self, '_custom_request') and self._engine is not None:
            data, sr = self._custom_request
            self._engine.set_custom_signal(data, sr)

    # ------------------------------------------------------------------
    def show_record(self, record: AnalysisResult | None) -> None:
        self._current = record
        if record is None:
            self.name_label.setText('No selection')
            self.meta_label.setText('')
            self.metric_label.setText('')
            self.tag_label.setText('')
            self.wave_item.setData(x=[], y=[])
            return
        name = record.path.replace('\\', '/').rsplit('/', 1)[-1]
        self.name_label.setText(name)
        self.name_label.setToolTip(record.path)
        self.meta_label.setText(
            f'{record.sample_rate} Hz · '
            f'{"mono" if record.channels == 1 else f"{record.channels} ch"} · '
            f'{record.effective_length_ms:.0f} ms eff / {record.length_ms:.0f} ms · '
            f'peak {record.peak_freq:.0f} Hz ({record.peak_db:+.1f} dB) · '
            f'notch {record.notch_freq:.0f} Hz ({record.notch_db:+.1f} dB)')
        self.bars.set_values(record.band_levels)
        self.metric_label.setText(
            f'Flatness {record.flatness_db:.2f} dB · '
            f'Tilt {record.tilt_db_oct:+.2f} dB/oct')
        self.tag_label.setText(' · '.join(record.tags) if record.tags else '—')
        x = np.linspace(0, 1, len(record.wave))
        self.wave_item.setData(x=x, y=record.wave)
