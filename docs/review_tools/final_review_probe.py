"""Read-only final review probes. Synthetic inputs; isolated Qt/cache state."""
from __future__ import annotations

import os
import sys
import json
import tempfile
import time
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
(ROOT / '.test-tmp').mkdir(exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='review-20260831-', dir=ROOT / '.test-tmp'))
os.environ['LOCALAPPDATA'] = str(OUT / 'localappdata')

import numpy as np
import soundfile as sf
from PySide6.QtCore import QSettings, QLocale, QEventLoop, QTimer, QThread
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication, QLabel, QFileDialog
from app.extensions.contracts import *
from app.extensions.preprocessing import prepare
from app.extensions.pair_compare import compare_pair, predict_blend
from app.extensions.processing import blend_sum, apply_alignment
from app.extensions.cache import FingerprintCache
from app.extensions.service import ResponseService
from app.extensions.ui.compare_workbench import CompareWorkbench
from app.extensions.ui.styles_boro import BORO_QSS
from app.core.cache import LibraryCache
from app.core.scanner import scan_library
from tests.extensions import fixtures as fx

results = {'output_directory': str(OUT)}

def prep(x, name='synthetic', sr=48000):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    x.setflags(write=False)
    return prepare(AudioBuffer(SourceKey(name, 0, x.nbytes, sr, x.shape[1]), x),
                   PreprocessingConfig())

# Independent endpoint oracle: at 100% B a crossfade must equal B.
sr = 48000
x = np.zeros(4096)
x[100] = 0.8
y = x * 0.25
a, b = prep(x, 'A'), prep(y, 'B')
cfg = PairComparisonConfig()
pair = compare_pair(a, b, cfg)
blend = predict_blend(a, b, cfg, alignment='onset')
mix, mix_sr, _ = blend_sum(a, b, pair, 1.0)
nfft = (len(blend.freqs) - 1) * 2
actual = 20 * np.log10(np.maximum(np.abs(np.fft.rfft(mix[:, 0], nfft)), 1e-30))
results['blend_endpoint'] = {
    'preview_100pct_b_db': float(np.median(blend.magnitude_db[-1])),
    'actual_100pct_b_db': float(np.median(actual)),
    'rms_mismatch_db': float(np.sqrt(np.mean((actual - blend.magnitude_db[-1])**2))),
    'self_reported_verification_db': blend.verified_rms_db,
}

# Raw versus onset timing and export onsets, with a known 120-sample delay.
late = np.pad(x, (120, 0))[:len(x)]
late_b = prep(late, 'delayed_B')
delay_pair = compare_pair(a, late_b, cfg)
aligned, _ = apply_alignment(late_b, IRProcessingConfig(delay_samples=delay_pair.delay_samples))
raw = predict_blend(a, late_b, cfg, alignment='raw')
onset = predict_blend(a, late_b, cfg, alignment='onset')
results['alignment'] = {
    'known_native_delay_samples': 120,
    'reported_delay_samples': delay_pair.delay_samples,
    'export_remaining_peak_delay_samples': int(np.argmax(abs(aligned[:,0])) - np.argmax(abs(a.data[:,0]))),
    'raw_vs_onset_max_db_difference': float(np.max(abs(raw.magnitude_db - onset.magnitude_db))),
}

# Same physical tone, two sample rates. Export ratio 100% B must preserve Hz.
t48 = np.arange(4800) / 48000
t96 = np.arange(9600) / 96000
p48 = prep(np.sin(2*np.pi*1000*t48)*np.exp(-t48/0.025), '48k', 48000)
p96 = prep(np.sin(2*np.pi*1000*t96)*np.exp(-t96/0.025), '96k', 96000)
rate_pair = PairComparisonResult(p48.key, p96.key, cfg, AnalysisStatus.OK, polarity=1)
mixed, mixed_sr, warnings = blend_sum(p48, p96, rate_pair, 1.0)
freq = np.fft.rfftfreq(65536, 1/mixed_sr)
results['different_sample_rates'] = {
    'input_b_tone_hz': 1000, 'input_b_sr': 96000, 'export_sr': mixed_sr,
    'export_peak_hz': float(freq[np.argmax(abs(np.fft.rfft(mixed[:,0], 65536)))]),
    'warnings': warnings,
}
silent = prep(np.zeros(4096), 'silent')
results['invalid_b_status'] = {
    'b_status': silent.status.value,
    'pair_status': compare_pair(a, silent, cfg).status.value,
    'blend_status': predict_blend(a, silent, cfg).status.value,
}
from app.extensions.pair_compare import _phase_diff_weighted
phase_rms, _ = _phase_diff_weighted(np.ones(2049, complex), -np.ones(2049, complex), cfg, sr)
results['phase_rms'] = {'expected_inverted_deg': 180.0, 'actual_deg': phase_rms}
from app.extensions.phase import compute_phase
stereo_one_silent = prep(np.column_stack((x, np.zeros_like(x))), 'stereo_one_silent')
stereo_phase = compute_phase(stereo_one_silent, PhaseConfig())
results['silent_stereo_channel_phase'] = {
    'finite_phase_bins_in_silent_channel': int(np.isfinite(stereo_phase.phase_rad[:,1]).sum()),
    'finite_group_delay_bins_in_silent_channel': int(np.isfinite(stereo_phase.group_delay_ms[:,1]).sum()),
}

# Library built solely from generated fixtures; no original IRs accessed.
lib = OUT / 'lib'
lib.mkdir()
for name, wave in [('a.wav', fx.boxy_fixture(300, 0.06, n=24000)),
                   ('b.wav', fx.clean_fixture(n=24000)),
                   ('c.wav', fx.decay_fixture(100, 0.02, n=24000))]:
    sf.write(lib / name, wave, 48000, subtype='FLOAT')
records = sorted(scan_library([str(lib)], LibraryCache(str(OUT/'legacy.json'))), key=lambda r:r.path)
cache = FingerprintCache(str(OUT/'response.db'))
service = ResponseService(cache=cache)
fp_a = service.fingerprint(records[0])
from app.extensions.fingerprint import CFG_HASH
with ThreadPoolExecutor(max_workers=1) as pool:
    worker_read = pool.submit(cache.get, fp_a.key.signature(), CFG_HASH).result()
    pool.submit(cache.put, replace(fp_a, key=replace(fp_a.key, path='worker-only')), CFG_HASH).result()
results['cross_thread_cache'] = {
    'main_thread_read_ok': cache.get(fp_a.key.signature(), CFG_HASH) is not None,
    'worker_read_ok': worker_read is not None,
    'count_after_worker_insert': cache.count(), 'expected_count': 2,
}

qapp = QApplication.instance() or QApplication([])
results['offscreen_fonts_before'] = len(QFontDatabase.families())
for font in ['segoeui.ttf', 'segoeuib.ttf', 'consola.ttf', 'consolab.ttf', 'seguisym.ttf', 'seguiemj.ttf']:
    QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / font))
qapp.setFont(QFont('Segoe UI', 9))
QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
results['offscreen_fonts_after'] = QFontDatabase.families()
qapp.setStyle('Fusion')
qapp.setStyleSheet(BORO_QSS)
wb = CompareWorkbench(service)
# Keep rendering deterministic: compute fixtures here, do not schedule live workers.
wb._debounce.timeout.disconnect()
wb.tabs.currentChanged.disconnect()
wb._on_tab_changed = lambda idx: None
wb.set_pair(records[0], records[1])
wb._debounce.stop()
pa, pb = service.prepared(records[0]), service.prepared(records[1])
result = {'pair': compare_pair(pa, pb, cfg),
          'blend': predict_blend(pa, pb, cfg),
          'env_a': service.envelope(records[0]), 'env_b': service.envelope(records[1])}
wb._pair_request_id = 42
wb._on_pair_done(42, result)
with patch.object(QFileDialog, 'getExistingDirectory', return_value='') as choose:
    wb.phase_blend.btn_export_b.click()
    wb.phase_blend.btn_export_blend.click()
    wb.phase_blend.btn_export_report.click()
    results['real_export_button_clicks'] = {'clicks': 3, 'directory_dialog_calls': choose.call_count}

# Keep the original request token then change B before the debounce launches new work.
wb.set_pair(records[0], records[2])
wb._debounce.stop()
wb._on_pair_done(42, result)
results['stale_during_debounce'] = {
    'selected_b': Path(wb.rec_b.path).name,
    'displayed_pair_b': Path(wb._last_pair.key_b.path).name,
    'status': wb.status.text(),
}
wb.set_pair(records[0], records[1])
wb._debounce.stop()
wb._on_pair_done(42, result)

# Real numerical cancellation with B polarity deliberately left inverted.
anti = prep(-2*x, 'inverted_B')
risky = predict_blend(a, anti, cfg, alignment='raw')
wb.phase_blend.show_blend(pair, risky)
results['comb_risk'] = {'computed_loss_db': risky.worst_cancellation_db,
                        'ui_badge': wb.phase_blend.comb_chip.text()}
wb.phase_blend.show_blend(result['pair'], result['blend'])

requests = []
wb.search.rank_requested.disconnect()
wb.search.rank_requested.connect(requests.append)
from app.extensions.ui.response_search_panel import PRESETS
preset_name = next(n for n in PRESETS if n != 'Custom')
wb.search._apply_preset(preset_name)
wb.search._emit()
results['search_preset'] = {'name': preset_name, 'defined_targets': PRESETS[preset_name][2],
                             'emitted_request': requests[-1]}

csd_a, csd_b = service.csd(records[0]), service.csd(records[1])
wb._apply_spec('csd_a', csd_a)
wb._apply_spec('csd_b', csd_b)
import pyqtgraph as pg
csd_images = [item for item in wb.csd._plot.getPlotItem().items if isinstance(item, pg.ImageItem)]
results['csd_renderer'] = {'class': type(wb.csd._renderer).__name__,
    'heatmap_count_after_a_then_b': len(csd_images),
    'only_image_equals_b': len(csd_images) == 1 and np.array_equal(csd_images[0].image, csd_b.magnitude_db.T),
    'numeric_text': wb.csd._decay_text.toPlainText()}
csd_valid = replace(csd_a, metrics={**csd_a.metrics, 'D20_40-120_ms': 100.0, 'D20_40-120_ms_valid': True})
wb.csd.show_csd(csd_valid)
results['csd_valid_metric_badge'] = wb.csd._decay_text.toPlainText().splitlines()[0]
wb.csd.show_csd(csd_b)
spec_a, spec_b = service.spectrogram(records[0]), service.spectrogram(records[1])
wb._apply_spec('spec_a', spec_a)
wb._apply_spec('spec_b', spec_b)
results['spectrogram_diff'] = {
    'a_time_frames': len(spec_a.times_ms), 'b_time_frames': len(spec_b.times_ms),
    'difference_image_count': sum(isinstance(i, pg.ImageItem) for i in wb.spectrogram._plots['diff'].getPlotItem().items),
    'footer': wb.spectrogram._diff_label.text(),
}
from app.extensions.spectrogram import compute_spectrogram
from app.extensions.ui.spectrogram_view import SpectrogramView
try:
    SpectrogramView().show_pair(compute_spectrogram(silent, TimeFrequencyConfig()), spec_b)
    results['invalid_spectrogram_ui'] = 'no error'
except Exception as exc:
    results['invalid_spectrogram_ui'] = f'{type(exc).__name__}: {exc}'
coverage = service.fingerprint(records[1]).all_features()['gd_valid_coverage'].value
results['display_units'] = {
    'coverage_fraction': coverage, 'expected_percent': coverage*100,
    'displayed_coverage': wb.summary._cards['gd_valid_coverage'].val_b_lbl.text(),
    'crest_factor_linear': service.envelope(records[1]).crest_factor,
}

def snapshot(widget, name, width, height):
    widget.resize(width, height)
    widget.show()
    qapp.processEvents()
    widget.grab().save(str(OUT / f'{name}.png'))
    labels = []
    for label in widget.findChildren(QLabel):
        if label.isVisible() and not label.wordWrap() and '\n' not in label.text():
            needed = label.fontMetrics().horizontalAdvance(label.text())
            if needed > label.contentsRect().width() + 5:
                labels.append({'text': label.text(), 'width': label.width(), 'text_px': needed})
    return {'requested': [width,height], 'actual': [widget.width(),widget.height()],
            'minimum_hint': [widget.minimumSizeHint().width(), widget.minimumSizeHint().height()],
            'potentially_clipped_labels': labels}

results['layouts'] = {}
for index, name in enumerate(['summary','waveform','csd','spectrogram','phase','search']):
    wb.tabs.setCurrentIndex(index)
    results['layouts'][name] = snapshot(wb, name, 1280, 880)
wb.tabs.setCurrentIndex(0)
results['layouts']['small_summary'] = snapshot(wb, 'small_summary', 1000, 700)
wb.tabs.setCurrentIndex(4)
results['layouts']['small_phase'] = snapshot(wb, 'small_phase', 1000, 700)
long_a = replace(records[0], path=str(lib / ('412_Vintage_Modern_Mix_Mic57_Mic121_OffAxis_CapEdge_Position03_48k_'*2 + 'A.wav')))
long_b = replace(records[1], path=str(lib / ('412_Vintage_Modern_Mix_Mic57_Mic121_OffAxis_CapEdge_Position03_48k_'*2 + 'B.wav')))
wb.deck.set_a(long_a)
wb.deck.set_b(long_b)
results['layouts']['long_filenames'] = snapshot(wb, 'long_filenames', 1000, 700)

# Include the actual inherited main screen with isolated user settings/cache.
import app.ui.main_window as legacy
from app.extensions.ui.main_window_adapter import ExtendedMainWindow
with patch.object(legacy, 'QSettings', lambda *args: QSettings(str(OUT/'settings.ini'), QSettings.IniFormat)), \
     patch('app.extensions.ui.main_window_adapter.ResponseService', return_value=service):
    main = ExtendedMainWindow()
    main.library = records
    main._on_scan_done(records)
    main.library_panel.table.selectRow(0)
    results['layouts']['main_large'] = snapshot(main, 'main_large', 1500, 900)
    results['layouts']['main_small'] = snapshot(main, 'main_small', 1280, 720)
    results['main_search_geometry'] = {'search_width': main.library_panel.search.width(),
        'library_width': main.library_panel.width(), 'screen_panel_min_width': main.screen_panel.minimumSizeHint().width()}
    main.close()

# Exercise one genuine background pair pipeline and observe GUI-thread work.
live_cache = FingerprintCache(str(OUT/'live-cache.db'))
live_service = ResponseService(cache=live_cache)
fingerprint_calls = []
original_fingerprint = live_service.fingerprint
def track_fingerprint(*args, **kwargs):
    start = time.perf_counter()
    fp = original_fingerprint(*args, **kwargs)
    fingerprint_calls.append({'on_gui_thread': QThread.currentThread() == qapp.thread(),
                              'elapsed_ms': (time.perf_counter()-start)*1000})
    return fp
live_service.fingerprint = track_fingerprint
live_wb = CompareWorkbench(live_service)
live_wb.set_pair(records[0], records[1])
live_wb._debounce.stop()
live_wb._compute_pair()
loop = QEventLoop()
live_wb._pair_worker.finished_ok.connect(loop.quit)
live_wb._pair_worker.failed.connect(loop.quit)
timeout = QTimer()
timeout.setSingleShot(True)
timeout.timeout.connect(loop.quit)
timeout.start(10000)
loop.exec()
timeout.stop()
live_wb._pair_worker.cancel()
live_wb._pair_worker.wait(5000)
results['live_pair_pipeline'] = {'completed': live_wb._last_pair is not None,
                                'fingerprint_calls': fingerprint_calls}
live_wb.close()
live_cache.close()
wb.close()
cache.close()
(OUT/'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(results, indent=2, ensure_ascii=True))
