"""Preset tonal targets expressed as per-band dB offsets (relative to overall mean).

Band map: Sub 20-60 | Low 60-120 | LowMid 120-350 | Mid 350-1k | MidHigh 1-3.5k
          High 3.5-8k | Air 8-20k  (Hz)

Values follow mainstream sound-engineering practice for electric guitar tones:
- Scoop core sits at 300-500 Hz ("boxy") and 800 Hz-1 kHz; presence/attack at
  3-5 kHz; palm-mute thump around 100 Hz; fizz low-pass ~10-12 kHz
  (Nail The Mix metal EQ guide, Music Guy Mixing, SevenString consensus).
- 2.5-8 kHz is the "presence & air" zone that lets guitars cut; 800 Hz-2.5 kHz
  pushes leads forward (Empress Effects guitar EQ guide).
- Vintage "brown tone" (Celestion G12M Greenback): low-mid warmth, smooth mids,
  natural roll-off above ~5 kHz, no fizz; Vintage 30 style modern voices add a
  2.3-5 kHz presence peak (Celestion specs, Midi Audio Expert IR analysis).
"""
from __future__ import annotations

from .analysis import BAND_NAMES

PRESETS: dict[str, dict[str, float]] = {
    'Flat': {b: 0.0 for b in BAND_NAMES},
    'Bright': {'Sub': -2.0, 'Low': -1.5, 'LowMid': -1.0, 'Mid': 0.0,
               'MidHigh': 1.5, 'High': 3.0, 'Air': 2.0},
    'Dark': {'Sub': 1.0, 'Low': 1.5, 'LowMid': 0.5, 'Mid': 0.0,
             'MidHigh': -1.5, 'High': -3.0, 'Air': -3.0},
    'Scooped': {'Sub': -2.0, 'Low': 2.0, 'LowMid': -1.0, 'Mid': -3.0,
                'MidHigh': 1.5, 'High': 3.0, 'Air': -2.0},
    'Mid-forward': {'Sub': -1.0, 'Low': -0.5, 'LowMid': -0.5, 'Mid': 2.5,
                    'MidHigh': 2.0, 'High': -0.5, 'Air': -1.0},
    'Tight low': {'Sub': -4.0, 'Low': -0.5, 'LowMid': 0.5, 'Mid': 0.5,
                  'MidHigh': 0.5, 'High': 1.0, 'Air': 0.0},
    'Vintage': {'Sub': -1.5, 'Low': 1.5, 'LowMid': 2.0, 'Mid': 1.0,
                'MidHigh': -1.0, 'High': -2.5, 'Air': -3.5},
}

PRESET_DESCRIPTIONS = {
    'Flat': 'Even response — a neutral canvas before amp/EQ shaping.',
    'Bright': 'Presence lift 3.5-8 kHz with cleaner lows — attack and mix cut '
              '(the classic "presence & air" zone).',
    'Dark': 'Tames 3-5 kHz harshness and rolls off 8 kHz+ fizz; warmth up front.',
    'Scooped': 'Modern metal stance: ~100 Hz palm-mute thump, 300-1 kHz boxiness '
               'scooped, 3-5 kHz presence, fizz low-passed above ~10 kHz.',
    'Mid-forward': 'Pushed 350 Hz-3.5 kHz so the guitar stays forward in a dense '
                   'mix (lead/forward zone per Empress guitar EQ guide).',
    'Tight low': 'High-pass character below ~100 Hz for fast, tight chugs; '
                 'mids kept honest.',
    'Vintage': 'Greenback-style "brown tone": 120-350 Hz low-mid warmth, vocal '
               'mids, smooth roll-off above ~5 kHz, no fizz.',
}
