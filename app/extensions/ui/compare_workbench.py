"""Compare A/B workbench (WP-07).

Two library rows populate A and B. Five tabs share the same source/config
identity; heavy computations run in workers with request IDs so stale results
never reach the plots, and results stay visible on failure.

Enhanced with Boro UI Design System:
- Dark Obsidian tactile layout
- Boro Golden Honey accents
- Dual-Deck Header for IR A (Electric Cyan) & IR B (Neon Emerald)
- Swap A/B action
- Glanceable acoustic metrics and comb risk alerts
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from app.core.analysis import AnalysisResult
from app.extensions.contracts import (AnalysisStatus, PairComparisonConfig,
                                      SourceKey, TimeFrequencyConfig,
                                      config_hash)
from app.extensions.service import ResponseService
from .csd_view import CsdView
from .phase_blend_view import PhaseBlendView
from .response_search_panel import ResponseSearchPanel
from .spectrogram_view import SpectrogramView
from .styles_boro import (ACCENT_GOLD, BORO_QSS, COLOR_IR_A, COLOR_IR_B,
                          FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY, SURFACE_CARD,
                          SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .summary_panel import SummaryPanel
from .waveform_view import WaveformView
from .widgets.ab_header import ABHeaderDeck
from .workers import AnalysisWorker, PairAnalysisWorker


def _short(path: str) -> str:
    return path.replace('\\', '/').rsplit('/', 1)[-1]


@dataclass(frozen=True)
class _SelectionContext:
    """Immutable A/B and analysis-config snapshot for asynchronous work."""

    generation: int
    a_path: str | None
    b_path: str | None
    a_key: SourceKey | None
    b_key: SourceKey | None
    pair_cfg: PairComparisonConfig
    tf_cfg: TimeFrequencyConfig
    config_hash: str


class CompareWorkbench(QDialog):
    """Modeless compare dialog owned by ExtendedMainWindow."""

    def __init__(self, service: ResponseService, parent=None):
        super().__init__(parent)
        self.setWindowTitle('BestIR — Compare A/B Workbench')
        self.setModal(False)
        self.resize(1280, 880)
        self.setStyleSheet(BORO_QSS)
        self.service = service

        self.rec_a: AnalysisResult | None = None
        self.rec_b: AnalysisResult | None = None
        self._selection_generation = 0
        self._selection_context: _SelectionContext | None = None
        self._pair_worker = None
        self._pair_request_id: int | None = None
        self._last_pair = None
        self._last_blend = None
        self._last_fp_a = None
        self._last_fp_b = None
        self._spec_workers = {}
        self._retired_workers = []
        self._spec_cache = {}
        self._csd_results = {}
        self._spec_results = {}
        self._spec_a = None
        self._spec_b = None

        # Boro A/B Header Deck
        self.deck = ABHeaderDeck(self)
        self.deck.set_a_requested.connect(self._set_a_from_selection)
        self.deck.set_b_requested.connect(self._set_b_from_selection)
        self.deck.swap_requested.connect(self._swap_ab)

        # Legacy compatibility aliases
        self.label_a = self.deck.card_a.name_lbl
        self.label_b = self.deck.card_b.name_lbl
        self.btn_a = self.deck.card_a.set_btn
        self.btn_b = self.deck.card_b.set_btn

        # Five core analysis tabs + Response Search
        self.summary = SummaryPanel()
        self.waveform = WaveformView()
        self.csd = CsdView()
        self.spectrogram = SpectrogramView()
        self.phase_blend = PhaseBlendView()
        self.phase_blend.set_export_enabled(False)
        # B05: route the view's export actions into the guarded workbench
        # handlers. Eligibility starts disabled; _invalidate() revokes it on
        # every selection change and _on_pair_done() restores it only for a
        # current, fully OK pair/blend result.
        self.phase_blend.export_aligned_b.connect(self._export_aligned_b)
        self.phase_blend.export_blend.connect(self._export_blend)
        self.phase_blend.export_report.connect(self._export_report)
        self.search = ResponseSearchPanel(self)
        self.search.rank_requested.connect(self._run_response_search)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.summary, '📊 Summary')
        self.tabs.addTab(self.waveform, '📈 Waveform & Envelope')
        self.tabs.addTab(self.csd, '🌊 CSD Waterfall')
        self.tabs.addTab(self.spectrogram, '🔥 Spectrogram Heatmaps')
        self.tabs.addTab(self.phase_blend, '⚡ Phase & Blend Prediction')
        self.tabs.addTab(self.search, '🎯 Response Search')

        self.status = QLabel('Select two IRs in the library to populate A/B.')
        self.status.setStyleSheet(f"""
            QLabel {{
                background-color: {SURFACE_CARD};
                border: 1px solid #222222;
                border-radius: 6px;
                padding: 6px 12px;
                color: {TEXT_MUTED};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.deck)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._compute_pair)

    # ---- A/B management -----------------------------------------------------
    def set_selection(self, records: list):
        """Called by ExtendedMainWindow on library selection changes."""
        if len(records) == 2:
            self.set_pair(records[0], records[1])
        elif len(records) == 1:
            if self.rec_a is None or self.rec_b is None or \
                    records[0].path not in (self.rec_a.path, self.rec_b.path):
                self._fill_slot(records[0])

    def _fill_slot(self, rec: AnalysisResult):
        if self.rec_a is None:
            self.set_a(rec)
        elif self.rec_b is None:
            self.set_b(rec)

    def set_pair(self, rec_a: AnalysisResult, rec_b: AnalysisResult):
        self.rec_a = rec_a
        self.rec_b = rec_b
        self.deck.set_a(rec_a)
        self.deck.set_b(rec_b)
        self._invalidate()

    def set_a(self, rec: AnalysisResult):
        self.rec_a = rec
        self.deck.set_a(rec)
        self._invalidate()

    def set_b(self, rec: AnalysisResult):
        self.rec_b = rec
        self.deck.set_b(rec)
        self._invalidate()

    def _swap_ab(self):
        if self.rec_a is not None or self.rec_b is not None:
            self.rec_a, self.rec_b = self.rec_b, self.rec_a
            self.deck.set_a(self.rec_a)
            self.deck.set_b(self.rec_b)
            self._invalidate()

    def _set_a_from_selection(self):
        rec = self._current_selection()
        if rec:
            self.set_a(rec)

    def _set_b_from_selection(self):
        rec = self._current_selection()
        if rec:
            self.set_b(rec)

    def _current_selection(self):
        parent = self.parent()
        getter = getattr(parent, 'selected_library_records', None)
        if getter:
            recs = getter()
            return recs[0] if recs else None
        return None

    @staticmethod
    def _normalized_path(path: str | None) -> str | None:
        if not path:
            return None
        return os.path.normcase(os.path.abspath(path))

    def _source_key_for(self, rec: AnalysisResult | None) -> SourceKey | None:
        if rec is None:
            return None
        try:
            stat = os.stat(rec.path)
        except OSError:
            return None
        return SourceKey(path=os.path.abspath(rec.path),
                         mtime_ns=stat.st_mtime_ns,
                         size=stat.st_size,
                         sample_rate=rec.sample_rate,
                         channels=rec.channels)

    def _capture_selection_context(self) -> _SelectionContext:
        pair_cfg = PairComparisonConfig()
        tf_cfg = TimeFrequencyConfig(profile='balanced')
        return _SelectionContext(
            generation=self._selection_generation,
            a_path=self._normalized_path(
                None if self.rec_a is None else self.rec_a.path),
            b_path=self._normalized_path(
                None if self.rec_b is None else self.rec_b.path),
            a_key=self._source_key_for(self.rec_a),
            b_key=self._source_key_for(self.rec_b),
            pair_cfg=pair_cfg,
            tf_cfg=tf_cfg,
            config_hash=config_hash({'pair': pair_cfg, 'time_frequency': tf_cfg}),
        )

    def _context_is_current(self, context: _SelectionContext | None) -> bool:
        return context is not None and context is self._selection_context

    def _record_matches_context(self, rec: AnalysisResult,
                                cache_key: str,
                                context: _SelectionContext) -> bool:
        expected_path = (context.a_path if cache_key.endswith('_a')
                         else context.b_path)
        return self._normalized_path(rec.path) == expected_path

    def _key_matches_context(self, key: SourceKey | None, slot: str,
                             context: _SelectionContext) -> bool:
        expected_path = context.a_path if slot == 'a' else context.b_path
        expected_key = context.a_key if slot == 'a' else context.b_key
        if key is None or self._normalized_path(key.path) != expected_path:
            return False
        return expected_key is None or key == expected_key

    @staticmethod
    def _result_config_hash(result) -> str | None:
        cfg = getattr(result, 'cfg', None)
        getter = getattr(cfg, 'config_hash', None)
        return getter() if callable(getter) else None

    def _pair_results_match_context(self, pair, blend,
                                    context: _SelectionContext) -> bool:
        expected_hash = context.pair_cfg.config_hash()
        return (
            self._key_matches_context(getattr(pair, 'key_a', None), 'a', context)
            and self._key_matches_context(getattr(pair, 'key_b', None), 'b', context)
            and self._key_matches_context(getattr(blend, 'key_a', None), 'a', context)
            and self._key_matches_context(getattr(blend, 'key_b', None), 'b', context)
            and self._result_config_hash(pair) == expected_hash
            and self._result_config_hash(blend) == expected_hash
        )

    def _spec_result_matches_context(self, cache_key: str, result,
                                     context: _SelectionContext) -> bool:
        slot = 'a' if cache_key.endswith('_a') else 'b'
        return (
            self._key_matches_context(getattr(result, 'key', None), slot, context)
            and self._result_config_hash(result) == context.tf_cfg.config_hash()
        )

    @staticmethod
    def _cancel_worker(worker) -> None:
        cancel = getattr(worker, 'cancel', None)
        if callable(cancel):
            cancel()

    def _retire_worker(self, worker) -> None:
        if worker is None:
            return
        if worker not in self._retired_workers:
            self._retired_workers.append(worker)
            finished = getattr(worker, 'finished', None)
            if finished is not None:
                finished.connect(
                    lambda retired=worker: self._retired_workers.remove(retired)
                    if retired in self._retired_workers else None)
        self._cancel_worker(worker)

    def _invalidate(self):
        self._selection_generation += 1
        self._selection_context = self._capture_selection_context()
        self._debounce.stop()

        self._pair_request_id = None
        if self._pair_worker is not None:
            self._retire_worker(self._pair_worker)
        self._pair_worker = None
        for worker in self._spec_workers.values():
            self._retire_worker(worker)
        self._spec_workers.clear()

        self._last_pair = None
        self._last_blend = None
        self._last_fp_a = None
        self._last_fp_b = None
        self._spec_cache.clear()
        self._csd_results.clear()
        self._spec_results.clear()
        self._spec_a = None
        self._spec_b = None
        self.phase_blend.set_export_enabled(False)
        self.phase_blend.show_pair(None, None, None)

        if self.rec_a is None or self.rec_b is None:
            self.status.setText('Assign both A and B to compare.')
            return
        self.status.setText(f'Comparing {_short(self.rec_a.path)} ↔ '
                            f'{_short(self.rec_b.path)} — analyzing…')
        self._debounce.start()

    # ---- pair pipeline ---------------------------------------------------------
    def _compute_pair(self, context: _SelectionContext | None = None):
        context = context or self._selection_context
        if (not self._context_is_current(context) or self.rec_a is None or
                self.rec_b is None or
                not self._record_matches_context(self.rec_a, 'pair_a', context) or
                not self._record_matches_context(self.rec_b, 'pair_b', context)):
            return
        if self._pair_worker and self._pair_worker.isRunning():
            self._retire_worker(self._pair_worker)
        a, b = self.rec_a, self.rec_b
        worker = PairAnalysisWorker(self.service, a, b, cfg=context.pair_cfg)
        worker.finished_ok.connect(
            lambda request_id, result, ctx=context:
            self._on_pair_done(request_id, result, ctx))
        worker.failed.connect(
            lambda request_id, msg, ctx=context:
            self._on_pair_failed(request_id, msg, ctx))
        self._pair_worker = worker
        self._pair_request_id = worker.request_id
        worker.start()

    def _on_pair_done(self, request_id: int, result: dict,
                      context: _SelectionContext | None = None):
        if self._pair_request_id != request_id:
            return   # stale result — ignore
        if context is not None and not self._context_is_current(context):
            return   # stale result — ignore
        active_context = self._selection_context
        if active_context is None or not isinstance(result, dict):
            return
        pair = result.get('pair')
        blend = result.get('blend')
        if not self._pair_results_match_context(pair, blend, active_context):
            return

        self.phase_blend.set_export_enabled(False)
        self._last_pair = pair
        self._last_blend = blend
        env_a, env_b = result['env_a'], result['env_b']
        # B17: fingerprint/phase arrive ready from the worker bundle; the
        # callback only renders — no service DSP runs on the GUI thread.
        self._last_fp_a = result.get('fp_a')
        self._last_fp_b = result.get('fp_b')
        self.waveform.show_envelopes(env_a, env_b)
        self.waveform.mark_onset_peak(env_a, COLOR_IR_A, 'A')
        self.waveform.mark_onset_peak(env_b, COLOR_IR_B, 'B')
        self.summary.show_fingerprints(
            self._last_fp_a, self._last_fp_b,
            _short(self.rec_a.path), _short(self.rec_b.path))
        self.phase_blend.show_pair(result.get('phase_a'),
                                   result.get('phase_b'), pair)
        self.phase_blend.show_blend(pair, blend)
        self.status.setText(f"Pair: delay {pair.delay_ms:+.2f} ms "
                            f"({pair.delay_samples:+.2f} samples), "
                            f"polarity {'same' if pair.polarity > 0 else 'INVERTED'}, "
                            f"correlation confidence {pair.correlation_confidence:.2f}")
        if (getattr(pair, 'status', None) == AnalysisStatus.OK and
                getattr(blend, 'status', None) == AnalysisStatus.OK):
            self.phase_blend.set_export_enabled(True)
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_pair_failed(self, request_id: int, msg: str,
                        context: _SelectionContext | None = None):
        if self._pair_request_id != request_id:
            return
        if context is not None and not self._context_is_current(context):
            return
        if self._selection_context is None:
            return
        self.phase_blend.set_export_enabled(False)
        self.status.setText(f'Pair analysis failed: {msg}')

    # ---- tab-driven heavy views ---------------------------------------------------
    def _on_tab_changed(self, idx: int):
        if self.rec_a is None or self.rec_b is None:
            return
        title = self.tabs.tabText(idx)
        if 'CSD' in title:
            self._ensure_spec('csd_a', self.rec_a)
            self._ensure_spec('csd_b', self.rec_b)
        elif 'Spectrogram' in title:
            self._ensure_spec('spec_a', self.rec_a, spectrogram=True)
            self._ensure_spec('spec_b', self.rec_b, spectrogram=True)

    def _ensure_spec(self, cache_key: str, rec: AnalysisResult,
                     spectrogram: bool = False):
        context = self._selection_context
        if (not self._context_is_current(context) or
                not self._record_matches_context(rec, cache_key, context)):
            return
        if cache_key in self._spec_cache:
            cached = self._spec_cache[cache_key]
            if self._spec_result_matches_context(cache_key, cached, context):
                self._apply_spec(cache_key, cached)
            else:
                self._spec_cache.pop(cache_key, None)
            return
        worker_key = cache_key
        old = self._spec_workers.get(worker_key)
        if old and old.isRunning():
            self._retire_worker(old)

        from app.extensions.csd import compute_csd
        from app.extensions.spectrogram import compute_spectrogram

        def job(worker):
            prepared = self.service.prepared(rec)
            return (compute_spectrogram(prepared, context.tf_cfg) if spectrogram
                    else compute_csd(prepared, context.tf_cfg))

        worker = AnalysisWorker(job)
        worker._selection_context = context
        worker.finished_ok.connect(
            lambda rid, res, key=cache_key, ctx=context:
            self._on_spec_done(key, rid, res, ctx))
        worker.failed.connect(
            lambda rid, msg, key=cache_key, ctx=context:
            self._on_spec_failed(key, rid, msg, ctx))
        self._spec_workers[worker_key] = worker
        worker.start()

    def _spec_callback_is_current(self, cache_key: str, request_id: int,
                                  context: _SelectionContext | None) -> bool:
        worker = self._spec_workers.get(cache_key)
        if worker is None or getattr(worker, 'request_id', None) != request_id:
            return False
        worker_context = getattr(worker, '_selection_context', None)
        if worker_context is not None and not self._context_is_current(worker_context):
            return False
        if context is not None:
            if not self._context_is_current(context):
                return False
            if worker_context is not None and context is not worker_context:
                return False
        return self._selection_context is not None

    def _on_spec_done(self, *args):
        if len(args) == 2:
            request_id, result = args
            matches = [k for k, worker in self._spec_workers.items()
                       if getattr(worker, 'request_id', None) == request_id]
            if len(matches) != 1:
                return
            cache_key = matches[0]
            context = getattr(self._spec_workers[cache_key],
                              '_selection_context', None)
        elif len(args) == 3:
            cache_key, request_id, result = args
            context = None
        elif len(args) == 4:
            cache_key, request_id, result, context = args
        else:
            return
        if not self._spec_callback_is_current(cache_key, request_id, context):
            return
        active_context = self._selection_context
        if active_context is None or not self._spec_result_matches_context(
                cache_key, result, active_context):
            return
        self._spec_cache[cache_key] = result
        self._apply_spec(cache_key, result)

    def _on_spec_failed(self, *args):
        if len(args) == 2:
            request_id, msg = args
            matches = [k for k, worker in self._spec_workers.items()
                       if getattr(worker, 'request_id', None) == request_id]
            if len(matches) != 1:
                return
            cache_key = matches[0]
            context = getattr(self._spec_workers[cache_key],
                              '_selection_context', None)
        elif len(args) == 3:
            cache_key, request_id, msg = args
            context = None
        elif len(args) == 4:
            cache_key, request_id, msg, context = args
        else:
            return
        if not self._spec_callback_is_current(cache_key, request_id, context):
            return
        self.status.setText(f'{cache_key} analysis failed: {msg}')

    def _apply_spec(self, cache_key: str, result):
        a_first = cache_key.endswith('_a')
        if cache_key.startswith('csd'):
            self._csd_results = getattr(self, '_csd_results', {})
            self._csd_results['a' if a_first else 'b'] = result
            ra = self._csd_results.get('a')
            rb = self._csd_results.get('b')
            if a_first:
                self.csd.show_csd(result, 'A')
            else:
                self.csd.show_csd(result, 'B')
        else:
            self._spec_results = getattr(self, '_spec_results', {})
            self._spec_results['a' if a_first else 'b'] = result
            if a_first:
                self._spec_a = result
            else:
                self._spec_b = result
            if getattr(self, '_spec_a', None) and getattr(self, '_spec_b', None):
                self.spectrogram.show_pair(self._spec_a, self._spec_b)
                self.spectrogram.show_metrics(
                    self._spec_a.metrics, self._spec_b.metrics)

    # ---- WP-08: non-destructive export ----------------------------------------------
    def _export_ready(self) -> bool:
        """B05 gate: exports require a current, fully valid pair/blend result.

        True only while the stored results belong to the active selection
        context (same A/B identity, config hash and generation) and both
        analyses completed cleanly.  Cleared immediately by ``_invalidate()``
        on any selection change, so stale results can never reach an export.
        """
        context = self._selection_context
        pair, blend = self._last_pair, self._last_blend
        if (context is None or pair is None or blend is None or
                self.rec_a is None or self.rec_b is None):
            return False
        if (getattr(pair, 'status', None) != AnalysisStatus.OK or
                getattr(blend, 'status', None) != AnalysisStatus.OK):
            return False
        return self._pair_results_match_context(pair, blend, context)

    def _export_pair(self):
        """Shared precondition + directory picker; None means do not export."""
        from PySide6.QtWidgets import QFileDialog
        if self.rec_a is None or self.rec_b is None:
            self.status.setText('Assign both A and B first.')
            return None
        if not self._export_ready():
            self.status.setText('Export unavailable: run the pair analysis '
                                'first — results are invalid or stale.')
            return None
        dest = QFileDialog.getExistingDirectory(self, 'Export processed IRs to…')
        return dest or None

    def _export_aligned_b(self):
        dest = self._export_pair()
        if not dest:
            return
        from app.extensions.contracts import IRProcessingConfig
        from app.extensions.processing_export import export_pair_aligned_b
        pair = self._last_pair
        cfg = IRProcessingConfig(normalize_peak_dbfs=-1.0,
                                 note='suggested alignment from Compare A/B')
        try:
            prep_a = self.service.prepared(self.rec_a)
            prep_b = self.service.prepared(self.rec_b)
            report = export_pair_aligned_b(prep_a, prep_b, pair, dest, cfg=cfg,
                                           suffix='aligned')
        except Exception as exc:   # B05: surface I/O/analysis failures in UI
            self.status.setText(f'Aligned-B export failed: {exc}')
            return
        self.status.setText(f"Exported {report.output_path.rsplit(chr(92), 1)[-1]} "
                            f"(delay {pair.delay_samples:+.2f} samples, polarity "
                            f"{pair.polarity:+d})")

    def _export_blend(self):
        dest = self._export_pair()
        if not dest:
            return
        from app.extensions.processing_export import export_blend
        pair = self._last_pair
        ratio = self.phase_blend.current_ratio_b()
        try:
            prep_a = self.service.prepared(self.rec_a)
            prep_b = self.service.prepared(self.rec_b)
            report = export_blend(prep_a, prep_b, pair, ratio, dest)
        except Exception as exc:   # B05: surface I/O/analysis failures in UI
            self.status.setText(f'Blend export failed: {exc}')
            return
        self.status.setText(f"Exported blend → "
                            f"{report.output_path.rsplit(chr(92), 1)[-1]}")

    def _export_report(self):
        dest = self._export_pair()
        if not dest:
            return
        from app.extensions.processing_export import export_pair_report
        pair = self._last_pair
        blend = self._last_blend
        try:
            report = export_pair_report(
                pair, blend,
                self._last_fp_a, self._last_fp_b,
                dest, name=f"pair_report_{_short(self.rec_a.path)}_vs_"
                           f"{_short(self.rec_b.path)}.json")
        except Exception as exc:   # B05: surface I/O failures in UI
            self.status.setText(f'Report export failed: {exc}')
            return
        self.status.setText(f"Exported report → {report.output_path}")

    # ---- response search ------------------------------------------------------------
    def _run_response_search(self, request: dict):
        records = getattr(self.parent(), 'library_records', lambda: [])()
        if not records:
            self.status.setText('No library loaded.')
            return
        anchor = self.rec_a or self.rec_b or records[0]
        target = anchor.curve_db

        def job(worker):
            from app.extensions.advanced_matching import rank_by_response
            fps = {}
            for i, r in enumerate(records[:400]):
                if worker.cancelled:
                    break
                fps[r.path] = self.service.fingerprint(r)
            return rank_by_response(records, fps, self.service, target,
                                    weights=request['weights'],
                                    constraints=request['constraints'],
                                    targets=request.get('targets'),  # B08
                                    policy=request['policy'])

        self.status.setText('Response search: fingerprinting shortlist…')
        worker = AnalysisWorker(job)
        worker.finished_ok.connect(self._on_search_done)
        worker.failed.connect(lambda rid, m: self.status.setText(
            f'Response search failed: {m}'))
        self._search_worker = worker
        worker.start()

    def _on_search_done(self, request_id: int, ranked):
        worker = getattr(self, '_search_worker', None)
        if not worker or worker.request_id != request_id:
            return
        self.search.show_results(ranked)
        self.status.setText(f'Response search: {len(ranked)} candidates ranked '
                            f'({sum(1 for c in ranked if not c.excluded)} eligible)')
