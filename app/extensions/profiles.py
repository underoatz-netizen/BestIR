"""Named analysis profiles (WP-05).

Profiles bundle a TimeFrequencyConfig with the persistence-band defaults so
views stay consistent. Boundaries are user-editable starting points, not
hard-coded definitions of "boxiness" (plan section 8.3).
"""
from __future__ import annotations

from .contracts import TimeFrequencyConfig

PERSISTENCE_PROFILES: dict[str, dict] = {
    'guitar_default': {
        'band': (180.0, 500.0),
        'neighbors': ((60.0, 180.0), (500.0, 2000.0)),
        'note': 'low-boxiness: persistent 180-500 Hz energy vs adjacent bands',
    },
    'low_bloom': {
        'band': (40.0, 120.0),
        'neighbors': ((120.0, 300.0),),
        'note': 'low-frequency bloom persistence vs upper neighbors',
    },
    'fizz': {
        'band': (6000.0, 12000.0),
        'neighbors': ((2000.0, 6000.0),),
        'note': 'high-frequency fizz persistence',
    },
}


def csd_profile(name: str) -> TimeFrequencyConfig:
    if name == 'low_end':
        return TimeFrequencyConfig(profile='low_end', fmin=20.0, fmax=1000.0,
                                   points_per_octave=48, dynamic_range_db=60.0)
    if name == 'high_res':
        return TimeFrequencyConfig(profile='high_res', fmin=100.0,
                                   fmax=20000.0, points_per_octave=24)
    return TimeFrequencyConfig(profile='balanced')


def spectrogram_profile(name: str) -> TimeFrequencyConfig:
    if name == 'low_end':
        return TimeFrequencyConfig(profile='low_end', fmin=20.0, fmax=2000.0,
                                   points_per_octave=48)
    if name == 'transient':
        return TimeFrequencyConfig(profile='transient')
    return TimeFrequencyConfig(profile='balanced')
