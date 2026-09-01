"""Frozen data contracts for the BestIR response extension (WP-01).

Every cross-module dataclass lives here and is treated as immutable by
convention: callers must not mutate result objects or their arrays. Numpy
arrays handed out by the adapter are flagged read-only; DSP code that needs to
mutate copies first.

Conventions (see docs/IR_COMPARISON_AND_MATCHING_PLAN_V2.md section 6):
- Samples are float64 shaped (frames, channels), finite values only.
- Configs carry an algorithm version and serialize deterministically
  (`config_hash`) for cache keys.
- Result arrays state their axes in the field name and units in comments.
- Nothing here is ever attached to legacy `AnalysisResult`.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

ALGO_VERSION = '1.0.0'


def deterministic_json(obj) -> str:
    """Stable JSON serialization for cache keys (no spaces, sorted keys)."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      default=_json_default)


def _json_default(obj):
    if isinstance(obj, np.ndarray):
        return [round(float(v), 6) for v in obj.tolist()]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f'Not JSON serializable: {type(obj)!r}')


def config_hash(obj) -> str:
    return hashlib.sha1(deterministic_json(obj).encode('utf-8')).hexdigest()[:16]


class AnalysisStatus(str, Enum):
    OK = 'ok'
    SILENT = 'silent'
    TOO_SHORT = 'too_short'
    NONFINITE = 'nonfinite'
    UNREADABLE = 'unreadable'
    INCOMPATIBLE = 'incompatible'


@dataclass(frozen=True)
class SourceKey:
    """Identity of a source file on disk (used for cache keys)."""
    path: str
    mtime_ns: int
    size: int
    sample_rate: int
    channels: int

    def signature(self) -> str:
        raw = f'{self.path}|{self.mtime_ns}|{self.size}|{self.sample_rate}|{self.channels}'
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class AudioBuffer:
    """Raw float64 samples (frames, channels), read-only, plus its source key."""
    key: SourceKey
    data: np.ndarray                 # (frames, channels) float64, non-writeable

    @property
    def sample_rate(self) -> int:
        return self.key.sample_rate

    @property
    def channels(self) -> int:
        return self.data.shape[1]

    @property
    def frames(self) -> int:
        return self.data.shape[0]


@dataclass(frozen=True)
class PreprocessingConfig:
    version: str = ALGO_VERSION
    dc_remove: bool = True
    onset_rel_threshold: float = 0.02      # fraction of peak magnitude
    noise_window_ms: float = 10.0          # pre-onset window for the noise floor
    tail_rel_threshold_db: float = -60.0   # vs peak-window RMS
    min_length_ms: float = 5.0
    max_length_ms: float = 4000.0          # analysis cap for very long files
    onset_backtrack_ms: float = 1.0        # keep this much pre-onset audio

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class PreparedIR:
    """Canonical per-file analysis input (WP-02 owns how it is built)."""
    key: SourceKey
    cfg: PreprocessingConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    data: np.ndarray | None = None         # processed copy, read-only (frames, ch)
    sample_rate: int = 0
    onset: int = 0                          # sample index of detected onset
    onset_confidence: float = 0.0           # 0..1
    peak_index: int = 0
    tail_end: int = 0                       # last useful sample index
    noise_floor_rms: float = 0.0
    peak_value: float = 0.0
    rms_value: float = 0.0

    @property
    def frames(self) -> int:
        return 0 if self.data is None else self.data.shape[0]

    @property
    def channels(self) -> int:
        return 0 if self.data is None else self.data.shape[1]

    def onset_ms(self) -> float:
        return self.onset / self.sample_rate * 1000.0 if self.sample_rate else 0.0

    def useful_ms(self) -> float:
        if not self.sample_rate:
            return 0.0
        return max(0, self.tail_end - self.onset) / self.sample_rate * 1000.0


@dataclass(frozen=True)
class EnvelopeConfig:
    version: str = ALGO_VERSION
    rms_window_ms: float = 2.0
    peak_hold: bool = True
    rise_from: float = 0.10
    rise_to: float = 0.90
    early_windows_ms: tuple = (1.0, 5.0)   # early-energy fraction windows
    late_from_ms: float = 5.0
    min_peak_gap_ms: float = 0.15          # rise-time validity: onset..peak gap

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class EnvelopeResult:
    key: SourceKey
    cfg: EnvelopeConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    time_ms: np.ndarray | None = None       # (frames,) onset-relative ms
    hilbert_env: np.ndarray | None = None   # (frames,) normalized 0..1
    rms_env: np.ndarray | None = None       # (frames,) normalized to its max
    peak_hold_env: np.ndarray | None = None
    peak_time_ms: float | None = None
    peak_polarity: int = 0                  # +1 / -1 / 0 unknown
    rise_time_ms: float | None = None       # None when not valid
    rise_valid: bool = False
    rise_reason: str = ''
    early_energy_1ms: float | None = None   # fraction of total energy
    early_energy_5ms: float | None = None
    early_late_ratio: float | None = None
    centroid_ms: float | None = None        # energy centroid (onset-relative)
    crest_factor: float | None = None
    tail_end_ms: float | None = None


@dataclass(frozen=True)
class TimeFrequencyConfig:
    version: str = ALGO_VERSION
    profile: str = 'balanced'    # low_end | balanced | high_res | transient
    fmin: float = 20.0
    fmax: float = 20000.0
    dynamic_range_db: float = 60.0
    points_per_octave: int = 24
    window: str = 'hann'
    reliability_floor_db: float = -70.0    # bins below (peak + floor) are invalid

    def config_hash(self) -> str:
        return config_hash(self)

    def window_ms(self) -> float:
        """Documented transform window length (ms) for the profile."""
        table = {'low_end': 80.0, 'balanced': 21.3, 'high_res': 10.7,
                 'transient': 5.3}
        return table.get(self.profile, 21.3)


@dataclass(frozen=True)
class CSDResult:
    key: SourceKey
    cfg: TimeFrequencyConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    freqs: np.ndarray | None = None        # (n_freq,) Hz
    times_ms: np.ndarray | None = None     # (n_time,) gate start, onset-relative
    magnitude_db: np.ndarray | None = None # (n_freq, n_time) rel to |H_0|
    valid_mask: np.ndarray | None = None   # (n_freq,) bool reliability mask
    gate_window_ms: np.ndarray | None = None  # (n_time,) effective window length
    band_decay: dict = field(default_factory=dict)   # band -> dB (n_time,)
    metrics: dict = field(default_factory=dict)      # scalars with validity


@dataclass(frozen=True)
class SpectrogramResult:
    key: SourceKey
    cfg: TimeFrequencyConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    freqs: np.ndarray | None = None        # (n_freq,) Hz
    times_ms: np.ndarray | None = None     # (n_time,) frame centers
    magnitude_db: np.ndarray | None = None # (n_freq, n_time) dB rel peak
    valid_mask: np.ndarray | None = None   # (n_freq,)
    window_ms: float = 0.0
    hop_ms: float = 0.0
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseConfig:
    version: str = ALGO_VERSION
    fmin: float = 30.0
    fmax: float = 18000.0
    rel_threshold_db: float = -60.0        # magnitude reliability vs peak bin
    unwrap_jump_rad: float = np.pi         # unwrap only below this residual jump
    min_phase: bool = True

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class PhaseResult:
    key: SourceKey
    cfg: PhaseConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    freqs: np.ndarray | None = None          # (n_freq,)
    phase_rad: np.ndarray | None = None      # (n_freq, n_ch) onset-compensated,
    #                                          unreliable bins set to NaN
    group_delay_ms: np.ndarray | None = None # (n_freq, n_ch) NaN where invalid
    valid_mask: np.ndarray | None = None     # (n_freq, n_ch) bool per channel
    min_phase_rad: np.ndarray | None = None  # (n_freq, n_ch) or None
    excess_phase_rad: np.ndarray | None = None
    coverage: float = 0.0                    # mean fraction of valid bins in band


@dataclass(frozen=True)
class PairComparisonConfig:
    version: str = ALGO_VERSION
    max_delay_ms: float = 10.0
    use_gcc_phat: bool = True
    blend_ratios: tuple = (0.0, 0.25, 0.5, 0.75, 1.0)   # gain of B in the mix
    risk_band: tuple = (80.0, 8000.0)
    reliability_floor_db: float = -60.0

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class PairComparisonResult:
    key_a: SourceKey
    key_b: SourceKey
    cfg: PairComparisonConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    delay_samples: float = 0.0     # B relative to A (B delayed by this much)
    delay_ms: float = 0.0
    polarity: int = 0              # +1 same, -1 inverted, 0 unknown
    correlation_confidence: float = 0.0
    phase_diff_weighted_rms_deg: float | None = None
    gd_median_diff_ms: np.ndarray | None = None   # (n_ch,) or None
    valid_fraction: float = 0.0
    onset_delay_samples: float = 0.0  # B onset relative to A at analysis rate
    residual_delay_samples: float = 0.0  # after detected-onset alignment
    source_sample_rate_a: int = 0
    source_sample_rate_b: int = 0
    analysis_sample_rate: int = 0
    reason: str = ''


@dataclass(frozen=True)
class CancellationRisk:
    """Cancellation evidence for one configured blend ratio."""
    worst_cancellation_db: float | None = None
    worst_cancellation_freq: float | None = None
    notch_freqs: tuple = ()
    sensitivity: Mapping[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class BlendPrediction:
    key_a: SourceKey
    key_b: SourceKey
    cfg: PairComparisonConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    freqs: np.ndarray | None = None
    magnitude_db: np.ndarray | None = None  # (n_ratios, n_freq) mix magnitude
    ratios: tuple = ()
    delay_samples: float = 0.0
    polarity: int = 1
    alignment: str = 'onset'   # raw | onset | suggested
    worst_cancellation_db: float | None = None
    worst_cancellation_freq: float | None = None
    notch_freqs: tuple = ()
    rms_deviation_db: float | None = None
    phase_compat_score: float | None = None   # 0..1, 1 = perfectly compatible
    sensitivity: dict = field(default_factory=dict)  # '+1'/'-1' -> worst cancel dB
    verified_rms_db: float | None = None      # prediction vs time-domain sum
    risk_by_ratio: Mapping[float, CancellationRisk] = field(default_factory=dict)
    onset_delay_samples: float = 0.0  # timing component applied to B
    residual_delay_samples: float = 0.0  # timing component applied to B
    source_sample_rate_a: int = 0
    source_sample_rate_b: int = 0
    analysis_sample_rate: int = 0
    reason: str = ''


@dataclass(frozen=True)
class DecayConfig:
    version: str = ALGO_VERSION
    bands: tuple = ((60.0, 120.0), (120.0, 350.0), (350.0, 1000.0))
    decay_targets_db: tuple = (10.0, 20.0, 30.0)
    schroeder_t: tuple = (20.0, 30.0)   # T20/T30 windows
    min_range_db: float = 25.0          # less usable range -> decay invalid

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class DecayResult:
    key: SourceKey
    cfg: DecayConfig
    status: AnalysisStatus
    warnings: tuple[str, ...] = ()
    band_decay_ms: dict = field(default_factory=dict)  # band -> ms to targets
    t20_ms: float | None = None
    t30_ms: float | None = None
    t60_estimate_ms: float | None = None   # Schroeder fit extrapolated to -60 dB
    t60_valid: bool = False
    t60_reason: str = 'not a valid reverberation measurement'


@dataclass(frozen=True)
class FeatureValue:
    """A scalar fingerprint field with explicit validity."""
    value: float | None
    valid: bool
    note: str = ''


@dataclass(frozen=True)
class ResponseFingerprint:
    key: SourceKey
    version: str = ALGO_VERSION
    cfg_hash: str = ''
    transient: dict = field(default_factory=dict)   # name -> FeatureValue
    decay: dict = field(default_factory=dict)
    phase: dict = field(default_factory=dict)

    def all_features(self) -> dict:
        out = {}
        out.update(self.transient)
        out.update(self.decay)
        out.update(self.phase)
        return out

    def to_json(self) -> str:
        return deterministic_json(self)

    @staticmethod
    def from_json(text: str) -> 'ResponseFingerprint':
        doc = json.loads(text)
        groups = {}
        for group in ('transient', 'decay', 'phase'):
            groups[group] = {
                name: FeatureValue(**feat)
                for name, feat in doc.get(group, {}).items()
            }
        return ResponseFingerprint(key=SourceKey(**doc['key']),
                                   version=doc['version'],
                                   cfg_hash=doc['cfg_hash'], **groups)


@dataclass(frozen=True)
class IRProcessingConfig:
    """Non-destructive processing recipe (WP-08).

    Populated ONLY after explicit user action from the suggested pair
    alignment; analysis never modifies audio on its own.
    """
    version: str = ALGO_VERSION
    delay_samples: float = 0.0    # advance B by this many samples (>0 = earlier)
    polarity: int = 1             # +1 keep, -1 invert
    normalize_peak_dbfs: float | None = None   # optional peak target, e.g. -1.0
    output_subtype: str = 'PCM_24'
    note: str = ''

    def config_hash(self) -> str:
        return config_hash(self)


@dataclass(frozen=True)
class ProcessingReport:
    """Provenance of one exported file (plan section 11.6)."""
    source_key: SourceKey
    output_path: str
    applied: dict = field(default_factory=dict)   # operation -> value (units in keys)
    warnings: tuple = ()
    algo_version: str = ALGO_VERSION

    def to_json(self) -> str:
        return deterministic_json(self)


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    raw_value: float | None
    norm_loss: float          # 0..1 normalized, 0 = perfect
    weight: float
    contribution: float       # norm_loss * weight
    valid: bool
    note: str = ''


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    components: tuple = ()    # tuple[ScoreComponent, ...]

    def explain(self) -> str:
        lines = [f'{c.name}: raw={c.raw_value} loss={c.norm_loss:.3f} '
                 f'w={c.weight:.2f} -> {c.contribution:.3f}'
                 f'{"" if c.valid else " [INVALID: " + c.note + "]"}'
                 for c in self.components]
        return '\n'.join(lines) + f'\ntotal = {self.total:.4f}'


@dataclass(frozen=True)
class RankedCandidate:
    record: object            # legacy AnalysisResult (read-only by convention)
    fingerprint: ResponseFingerprint | None
    breakdown: ScoreBreakdown | None
    rank: int = 0
    excluded: bool = False
    reason: str = ''
