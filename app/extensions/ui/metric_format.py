"""Display-only unit formatting for extension UI metrics (B12).

Cached raw values and contract semantics are NEVER modified:
- ``gd_valid_coverage`` is stored as a 0..1 fraction (``PhaseResult.coverage``)
- ``crest_factor`` is stored as a raw linear peak/RMS ratio (``envelope.py``)

Conversions happen only at render time:
- a fraction with display unit ``'%'`` is shown as ``value * 100`` with 2
  decimals (0.250978 -> ``25.10%``)
- a linear crest ratio shown in ``'dB'`` is converted via ``20*log10(ratio)``
  with a safe guard for zero/negative/non-finite input (-> ``n/a``)
- anything else is formatted in its raw unit unchanged

Pure functions only: no Qt, no legacy DSP imports.
"""
from __future__ import annotations

import math

#: features whose cached raw value is a 0..1 fraction displayed as percent
FRACTION_FEATURES = frozenset({'gd_valid_coverage'})
#: features whose raw value is a linear peak/RMS ratio (crest factor)
CREST_FEATURES = frozenset({'crest_factor'})

_INVALID_TEXT = 'n/a'


def crest_ratio_to_db(ratio: float | None) -> float | None:
    """Convert a linear peak/RMS ratio to dB (20*log10). Guarded: None,
    zero/negative or non-finite input returns None."""
    if ratio is None:
        return None
    r = float(ratio)
    if not math.isfinite(r) or r <= 0.0:
        return None
    return 20.0 * math.log10(r)


def to_display_value(feature: str, value: float | None,
                     unit: str) -> float | None:
    """Map a raw cached feature value to a value expressed in ``unit``.

    Returns None when the value cannot be shown in the requested unit
    (missing, non-finite, or crest ratio <= 0 for a dB display).
    """
    if value is None:
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    if unit == '%' or feature in FRACTION_FEATURES:
        return v * 100.0
    if feature in CREST_FEATURES and unit == 'dB':
        return crest_ratio_to_db(v)
    return v


def unit_suffix(unit: str) -> str:
    """Suffix text for a display unit ('%' attaches directly)."""
    if not unit:
        return ''
    return unit if unit == '%' else f' {unit}'


def format_number(value: float | None, unit: str, *, signed: bool = False,
                  sig: int = 4) -> str:
    """Format an already-converted display value as plain text (no suffix).

    Percent always uses 2 decimals; other units use significant digits.
    """
    if value is None:
        return _INVALID_TEXT
    v = float(value)
    if unit == '%':
        return f'{v:+.2f}' if signed else f'{v:.2f}'
    return f'{v:+.{sig}g}' if signed else f'{v:.{sig}g}'


def format_value(value: float | None, unit: str, *, signed: bool = False,
                 sig: int = 4) -> str:
    """Format an already-converted display value with its unit suffix.

    The invalid placeholder is shown alone (no dangling unit suffix).
    """
    text = format_number(value, unit, signed=signed, sig=sig)
    if text == _INVALID_TEXT:
        return text
    return text + unit_suffix(unit)


def format_cell(value: float | None, unit: str, *, signed: bool = False,
                sig: int = 4) -> str:
    """Format a mixed-unit table cell: percent rows get a '%' marker,
    all other rows keep the established bare-number cells."""
    text = format_number(value, unit, signed=signed, sig=sig)
    if text == _INVALID_TEXT or unit != '%':
        return text
    return text + '%'


def format_metric(feature: str, value: float | None, unit: str, *,
                  signed: bool = False, sig: int = 4) -> str:
    """Convert a raw cached value to the display unit and format it."""
    return format_value(to_display_value(feature, value, unit), unit,
                        signed=signed, sig=sig)
