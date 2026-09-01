"""Central stereo analysis channel policy (FINAL_REVIEW 2026-08-31).

Every extension DSP module that reduces channels to scalars must go through
this module so the channel policy is decided in ONE place:

- **Power aggregation**: magnitude/energy reductions use the mean of
  per-channel squares (RMS in amplitude units), never a signed channel mean.
  An anti-phase stereo pair ``[x, -x]`` keeps its energy instead of cancelling
  to near-silence.
- **Mono identity**: a single channel is used as-is. ``power_aggregate`` is
  exact for energy signals (mean(x**2) over one channel == x**2);
  ``mono_or_rms`` keeps signed magnitude signals byte-identical for mono and
  applies RMS power aggregation only when more than one channel exists.
- **Pair/blend**: equal channel counts only (``channel_count_matches``); there
  is no implicit mono<->stereo broadcasting, and channel mismatches stay
  ``INCOMPATIBLE`` in pair_preparation.
- **Per-channel evidence** (phase / group delay, B11): scalar summaries
  aggregate only valid channel entries (``valid_channel_aggregate``) and carry
  provenance about which channels contributed.
"""
from __future__ import annotations

import numpy as np


def power_aggregate(x, axis=-1):
    """Mean of per-axis squares (power aggregation over channels).

    Energy is preserved for any channel layout: ``[x, -x]`` -> mean(x**2),
    never a signed cancellation. For a single channel this equals x**2
    exactly, so mono energy consumers are byte-identical.
    """
    return np.mean(np.asarray(x, dtype=np.float64) ** 2, axis=axis)


def rms_aggregate(x, axis=-1):
    """Amplitude-scale variant of `power_aggregate` (sqrt of mean squares)."""
    return np.sqrt(power_aggregate(x, axis))


def mono_or_rms(x, axis=-1):
    """Channel reduction for SIGNED magnitude signals.

    A single channel is returned as-is (exact mono backward compatibility);
    multiple channels are power-aggregated to RMS so ``[x, -x]`` -> |x|
    instead of silence.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.shape[axis] <= 1:
        return x[(slice(None),) * axis + (0,)]
    return rms_aggregate(x, axis)


def channel_count_matches(a, b) -> bool:
    """True when both inputs carry the same channel count.

    Accepts PreparedIR / AudioBuffer (``.channels``), plain ints, or 2-D
    sample arrays (last axis = channels). No implicit mono<->stereo
    broadcasting is ever performed by pair/blend code.
    """
    def _n(v):
        if isinstance(v, int):
            return v
        if hasattr(v, 'channels'):
            return int(v.channels)
        return int(np.asarray(v).shape[-1])
    return _n(a) == _n(b)


def valid_channel_aggregate(values, valid, agg='median'):
    """Aggregate `values` over ONLY the entries where `valid` is True.

    Each channel contributes only its own evidence: a silent or anti-phase
    channel can never corrupt another channel's valid bins (B11 per-channel
    validity). The last axis of `valid` is treated as the channel axis.

    Returns ``(value, n_used, channels_used)``:
    - value: scalar aggregate (None when no valid entry exists)
    - n_used: number of valid entries that were aggregated
    - channels_used: tuple of channel indices with at least one valid entry

    `agg` is one of 'median', 'mean', 'p25', 'p75'.
    """
    values = np.asarray(values, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    if values.shape != valid.shape:
        raise ValueError('values and valid must share shape')
    used = values[valid]
    if used.size == 0:
        return None, 0, ()
    if agg == 'median':
        fn = np.median
    elif agg == 'mean':
        fn = np.mean
    elif agg == 'p25':
        fn = lambda a: np.percentile(a, 25)
    elif agg == 'p75':
        fn = lambda a: np.percentile(a, 75)
    else:
        raise ValueError(f'unknown agg {agg!r}')
    channels_used = tuple(int(c) for c in range(valid.shape[-1])
                          if valid[..., c].any())
    return float(fn(used)), int(used.size), channels_used