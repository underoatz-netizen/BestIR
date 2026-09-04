"""ResponseService facade (WP-01): one entry point for all extension analysis.

The service owns the preprocessing config and dispatches to the DSP modules.
Heavy modules are imported lazily so this file stays importable even when only
part of the extension is present.

Cost tiers:
- fingerprint(): Tier 1 — scalar only, SQLite-cached.
- csd()/spectrogram()/phase()/pair()/blend(): Tier 2 — computed on demand for
  selected IRs only, never persisted.
"""
from __future__ import annotations

import os

import numpy as np

from ..core.analysis import AnalysisResult
from .adapters import LegacyIRAdapter, make_read_only
from .cache import FingerprintCache
from .contracts import (ALGO_VERSION, AnalysisStatus, AudioBuffer,
                        BlendPrediction, CSDResult, DecayConfig, DecayResult,
                        EnvelopeConfig, EnvelopeResult, PairComparisonConfig,
                        PairComparisonResult, PhaseConfig, PhaseResult,
                        PreparedIR, PreprocessingConfig, ResponseFingerprint,
                        SourceKey, SpectrogramResult, TimeFrequencyConfig)

_UNPROCESSED = (AnalysisStatus.SILENT, AnalysisStatus.NONFINITE,
                AnalysisStatus.TOO_SHORT, AnalysisStatus.UNREADABLE)


class ResponseService:
    def __init__(self,
                 prep_cfg: PreprocessingConfig | None = None,
                 env_cfg: EnvelopeConfig | None = None,
                 tf_cfg: TimeFrequencyConfig | None = None,
                 phase_cfg: PhaseConfig | None = None,
                 decay_cfg: DecayConfig | None = None,
                 cache: FingerprintCache | None = None):
        self.adapter = LegacyIRAdapter()
        self.prep_cfg = prep_cfg or PreprocessingConfig()
        self.env_cfg = env_cfg or EnvelopeConfig()
        self.tf_cfg = tf_cfg or TimeFrequencyConfig()
        self.phase_cfg = phase_cfg or PhaseConfig()
        self.decay_cfg = decay_cfg or DecayConfig()
        self.cache = cache if cache is not None else FingerprintCache()
        self._buffer_cache: dict[str, AudioBuffer] = {}

    # ---- tier 0/1 ------------------------------------------------------------
    def load(self, record: AnalysisResult) -> AudioBuffer:
        """Load raw audio for one legacy record (small LRU by path+mtime)."""
        path = record.path
        cache_key = f'{path}|{os.path.getmtime(path) if os.path.exists(path) else 0}'
        buf = self._buffer_cache.get(cache_key)
        if buf is None:
            buf = self.adapter.load_path(path)
            if len(self._buffer_cache) > 8:
                self._buffer_cache.clear()
            self._buffer_cache[cache_key] = buf
        return buf

    def prepared(self, record: AnalysisResult) -> PreparedIR:
        from .preprocessing import prepare
        buf = self.load(record)
        return prepare(buf, self.prep_cfg)

    def envelope(self, record: AnalysisResult) -> EnvelopeResult:
        from .envelope import compute_envelope
        return compute_envelope(self.prepared(record), self.env_cfg)

    def fingerprint(self, record: AnalysisResult, force: bool = False
                    ) -> ResponseFingerprint:
        from .contracts import SourceKey
        from .fingerprint import compute_fingerprint, effective_cfg_hash
        signature = self._signature_for(record)
        cfg_hash = effective_cfg_hash(self)
        if not force:
            cached = self.cache.get(signature, cfg_hash)
            if cached is not None:
                return cached
        fp = compute_fingerprint(record, self)
        self.cache.put(fp, cfg_hash)
        return fp

    def _signature_for(self, record: AnalysisResult) -> str:
        """Cache signature without loading audio (same formula as SourceKey)."""
        stat = os.stat(record.path)
        key = SourceKey(path=os.path.abspath(record.path),
                        mtime_ns=stat.st_mtime_ns, size=stat.st_size,
                        sample_rate=record.sample_rate,
                        channels=record.channels)
        return key.signature()

    # ---- tier 2 ------------------------------------------------------------
    def csd(self, record: AnalysisResult, cfg=None) -> CSDResult:
        from .csd import compute_csd
        return compute_csd(self.prepared(record), cfg or self.tf_cfg)

    def spectrogram(self, record: AnalysisResult, cfg=None) -> SpectrogramResult:
        from .spectrogram import compute_spectrogram
        return compute_spectrogram(self.prepared(record), cfg or self.tf_cfg)

    def phase(self, record: AnalysisResult, cfg=None) -> PhaseResult:
        from .phase import compute_phase
        return compute_phase(self.prepared(record), cfg or self.phase_cfg)

    def decay(self, record: AnalysisResult, cfg=None) -> DecayResult:
        from .decay import compute_decay
        return compute_decay(self.prepared(record), cfg or self.decay_cfg)

    def pair(self, rec_a: AnalysisResult, rec_b: AnalysisResult,
             cfg: PairComparisonConfig | None = None) -> PairComparisonResult:
        from .pair_compare import compare_pair
        return compare_pair(self.prepared(rec_a), self.prepared(rec_b),
                            cfg or PairComparisonConfig())

    def blend(self, rec_a: AnalysisResult, rec_b: AnalysisResult,
              cfg: PairComparisonConfig | None = None) -> BlendPrediction:
        from .pair_compare import predict_blend
        return predict_blend(self.prepared(rec_a), self.prepared(rec_b),
                             cfg or PairComparisonConfig())
