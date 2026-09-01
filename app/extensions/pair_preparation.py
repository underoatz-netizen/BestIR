"""Shared full-buffer preparation for pair analysis and processing."""
from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy.signal import resample_poly

from .contracts import AnalysisStatus, PreparedIR


@dataclass(frozen=True)
class PreparedPair:
    """A and B on A's sample-rate/time-origin contract.

    Source ``PreparedIR`` objects remain unchanged.  ``data_a`` and ``data_b``
    retain their complete buffers so pair timing always includes leading silence.
    """
    status: AnalysisStatus
    reason: str = ''
    warnings: tuple[str, ...] = ()
    data_a: np.ndarray | None = None
    data_b: np.ndarray | None = None
    sample_rate: int = 0
    source_sample_rate_a: int = 0
    source_sample_rate_b: int = 0
    onset_a: int = 0
    onset_b: int = 0
    tail_end_a: int = 0
    tail_end_b: int = 0

    @property
    def onset_delay_samples(self) -> float:
        """Positive when B's detected onset is later than A's."""
        return float(self.onset_b - self.onset_a)


def prepare_pair(a: PreparedIR, b: PreparedIR) -> PreparedPair:
    """Return full buffers at A's rate, or an explicit invalid pair result."""
    rate_a = int(a.sample_rate)
    rate_b = int(b.sample_rate)
    if a.status != AnalysisStatus.OK or b.status != AnalysisStatus.OK:
        status = (AnalysisStatus.TOO_SHORT if AnalysisStatus.TOO_SHORT in
                  (a.status, b.status) else
                  (a.status if a.status != AnalysisStatus.OK else b.status))
        reason = f'cannot prepare pair: A={a.status.value}, B={b.status.value}'
        return _invalid_pair(status, reason, a, b, rate_a, rate_b)
    if a.data is None or b.data is None:
        return _invalid_pair(AnalysisStatus.INCOMPATIBLE,
                             'cannot prepare pair: missing audio data', a, b,
                             rate_a, rate_b)
    if a.data.ndim != 2 or b.data.ndim != 2:
        return _invalid_pair(AnalysisStatus.INCOMPATIBLE,
                             'cannot prepare pair: audio data must be (frames, channels)',
                             a, b, rate_a, rate_b)

    # Reject this before copying or resampling either source.
    channels_a, channels_b = a.data.shape[1], b.data.shape[1]
    if channels_a != channels_b:
        return _invalid_pair(
            AnalysisStatus.INCOMPATIBLE,
            f'channel mismatch: A has {channels_a} channel(s), '
            f'B has {channels_b} channel(s)',
            a, b, rate_a, rate_b,
        )
    if rate_a <= 0 or rate_b <= 0:
        return _invalid_pair(AnalysisStatus.INCOMPATIBLE,
                             f'invalid sample rate: A={rate_a} Hz, B={rate_b} Hz',
                             a, b, rate_a, rate_b)

    data_a = np.array(a.data, dtype=np.float64, copy=True)
    warnings: tuple[str, ...] = ()
    if rate_a == rate_b:
        data_b = np.array(b.data, dtype=np.float64, copy=True)
        up = down = 1
    else:
        divisor = gcd(rate_a, rate_b)
        up, down = rate_a // divisor, rate_b // divisor
        data_b = np.asarray(resample_poly(b.data, up, down, axis=0),
                            dtype=np.float64)
        warnings = (
            f'B resampled from {rate_b} Hz to A analysis/output rate '
            f'{rate_a} Hz (ratio {up}/{down})',
        )

    data_a.setflags(write=False)
    data_b.setflags(write=False)
    return PreparedPair(
        status=AnalysisStatus.OK,
        warnings=warnings,
        data_a=data_a,
        data_b=data_b,
        sample_rate=rate_a,
        source_sample_rate_a=rate_a,
        source_sample_rate_b=rate_b,
        onset_a=_clamp_index(a.onset, len(data_a)),
        onset_b=_scale_index(b.onset, up, down, len(data_b)),
        tail_end_a=_clamp_index(a.tail_end, len(data_a)),
        tail_end_b=_scale_index(b.tail_end, up, down, len(data_b)),
    )


def _invalid_pair(status: AnalysisStatus, reason: str, a: PreparedIR,
                  b: PreparedIR, rate_a: int, rate_b: int) -> PreparedPair:
    return PreparedPair(
        status=status,
        reason=reason,
        warnings=tuple(a.warnings) + tuple(b.warnings) + (reason,),
        sample_rate=rate_a,
        source_sample_rate_a=rate_a,
        source_sample_rate_b=rate_b,
    )


def _clamp_index(index: int, frames: int) -> int:
    return min(max(int(index), 0), max(frames - 1, 0))


def _scale_index(index: int, up: int, down: int, frames: int) -> int:
    return _clamp_index(round(int(index) * up / down), frames)
