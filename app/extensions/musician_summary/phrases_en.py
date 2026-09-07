"""English phrase templates and dictionary for Musician Summary.

Mirrors phrases_th.py with natural musician English:
- Strict separation of tonal balance (magnitude) and temporal response (decay/attack).
- No winner bias or psychoacoustic overclaims.
- Clear evidence-to-character phrasing.
"""
from __future__ import annotations

# Identical
IDENTICAL_OVERVIEW = "Based on measured values, both IRs share very similar tonal balance and temporal response with no prominent differences."
IDENTICAL_DESC_A = "Tone and decay are very close to B."
IDENTICAL_DESC_B = "Tone and decay are very close to A."
IDENTICAL_FOCUS = (
    "Audition A/B with identical DI and level-matched to listen for subtle nuances.",
)

# Tone differences
TONE_SIMILAR = "Overall tonal balance is very close"
TONE_DIFF_LOW_MORE_A = "A carries more low-end weight than B"
TONE_DIFF_LOW_MORE_B = "B carries more low-end weight than A"
TONE_DIFF_LOWMID_MORE_A = "A has more low-mid energy, leaning towards a thicker body"
TONE_DIFF_LOWMID_MORE_B = "B has more low-mid energy, leaning towards a thicker body"
TONE_DIFF_MID_MORE_A = "A has a more prominent midrange"
TONE_DIFF_MID_MORE_B = "B has a more prominent midrange"
TONE_DIFF_HIGH_MORE_A = "A has a more open and brighter top end than B"
TONE_DIFF_HIGH_MORE_B = "B has a more open and brighter top end than A"

# Decay differences
DECAY_SIMILAR = "Tail decay response is very similar"
DECAY_LOW_FASTER_A = "A has a shorter low-end tail (decays faster in the low-end)"
DECAY_LOW_FASTER_B = "B has a shorter low-end tail (decays faster in the low-end)"
DECAY_LOW_LONGER_A = "A has a longer low-end tail than B"
DECAY_LOW_LONGER_B = "B has a longer low-end tail than A"
BOXINESS_EXCESS_A = "A has localized low-mid resonance persisting longer; check if it adds body or sounds boxy on heavy riffs"
BOXINESS_EXCESS_B = "B has localized low-mid resonance persisting longer; check if it adds body or sounds boxy on heavy riffs"

# Attack / Transient differences
ATTACK_EARLIER_A = "A concentrates more energy at onset, tending to give a more prominent pick attack"
ATTACK_EARLIER_B = "B concentrates more energy at onset, tending to give a more prominent pick attack"

# Phase / Group delay
PHASE_TIMING_DIFF = "Response timing varies across certain frequency bands"

# Blend
BLEND_NO_LOSS = "At 50/50 blend, no significant phase cancellation or notch loss is detected"
BLEND_CANCEL_WARN = "At 50/50 blend, {band} drops by {loss:.1f} dB due to phase cancellation"
BLEND_NOT_READY = "Blend compatibility is not yet evaluated; verify pair analysis first"

# Listening focus recommendations
FOCUS_PALM_MUTE_DECAY = "Use identical DI and level-match, then audition palm-mutes with sudden stops to observe low-end tail damping"
FOCUS_PICK_ATTACK = "Compare the initial pick strike on the lower strings to evaluate attack sharpness and transient feel"
FOCUS_LOW_WEIGHT = "Audition open chords and deep bass notes to compare low-end weight and body density"
FOCUS_HIGH_OPENNESS = "Listen to top-end harmonics and chime to decide between an open cut versus smooth warmth"
FOCUS_BOXINESS = "Check whether low-mid energy supports guitar body thickness or creates boxiness in the mix"

# Limitations / Edge cases
LIMIT_B_TOO_SHORT_DECAY = "Tone is comparable, but B is too short to evaluate low-end decay"
LIMIT_A_TOO_SHORT_DECAY = "Tone is comparable, but A is too short to evaluate low-end decay"
LIMIT_NO_DECAY_DATA = "Insufficient decay data to evaluate tail damping"
LIMIT_INVALID_FILE_A = "File A cannot be fully read or measured"
LIMIT_INVALID_FILE_B = "File B cannot be fully read or measured"
LIMIT_NO_PAIR_ANALYSIS = "Pair blend compatibility has not been evaluated"
