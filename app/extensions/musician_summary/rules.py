"""Pure evaluation rules for Musician Summary.

Translates SummarySnapshot metrics into Claims and MusicianSummary:
- Strictly separates tone (magnitude) vs temporal response (decay/attack).
- Directional swap symmetry: comparing B to A produces exact inverted claims without bias.
- Respects data validity and limits; never hallucinates values.
- Offline, pure Python, no Qt, no DSP recalculations.
"""
from __future__ import annotations

from typing import List, Tuple

from .contracts import Claim, Language, MusicianSummary, SummarySnapshot
from . import phrases_en, phrases_th


# Calibrated acoustic difference thresholds
THRESH_TONE_DB = 1.0          # Band level difference >= 1.0 dB to claim prominence
THRESH_D20_RATIO = 0.15       # >= 15% change in low-end decay time
THRESH_ATTACK_RATIO = 0.20    # >= 20% change in onset energy or rise time
THRESH_BOXINESS_DB = 2.0      # Persistence excess >= 2 dB
THRESH_BLEND_LOSS_DB = -3.0   # Cancellation loss worse than -3 dB


def evaluate_claims(snapshot: SummarySnapshot) -> list[Claim]:
    """Extract evidenced claims from snapshot."""
    claims: list[Claim] = []

    if snapshot.identical:
        claims.append(Claim(
            claim_id='identical',
            subject='both',
            category='identity',
            template_key='IDENTICAL',
            evidence_ids=('identical_input',),
        ))
        return claims

    # 1. Tone Claims
    bands_a = snapshot.bands_a
    bands_b = snapshot.bands_b
    all_bands = set(bands_a.keys()).intersection(set(bands_b.keys()))

    # Low band
    if 'Low' in all_bands:
        delta_low = bands_a['Low'] - bands_b['Low']
        if delta_low >= THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_low_more_a',
                subject='A',
                category='tone',
                template_key='TONE_DIFF_LOW_MORE_A',
                template_params={'delta_db': delta_low},
                evidence_ids=('bands.Low',),
            ))
        elif delta_low <= -THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_low_more_b',
                subject='B',
                category='tone',
                template_key='TONE_DIFF_LOW_MORE_B',
                template_params={'delta_db': -delta_low},
                evidence_ids=('bands.Low',),
            ))

    # Low-Mid band
    if 'LowMid' in all_bands:
        delta_lm = bands_a['LowMid'] - bands_b['LowMid']
        if delta_lm >= THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_lowmid_more_a',
                subject='A',
                category='tone',
                template_key='TONE_DIFF_LOWMID_MORE_A',
                template_params={'delta_db': delta_lm},
                evidence_ids=('bands.LowMid',),
            ))
        elif delta_lm <= -THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_lowmid_more_b',
                subject='B',
                category='tone',
                template_key='TONE_DIFF_LOWMID_MORE_B',
                template_params={'delta_db': -delta_lm},
                evidence_ids=('bands.LowMid',),
            ))

    # Mid band
    if 'Mid' in all_bands:
        delta_m = bands_a['Mid'] - bands_b['Mid']
        if delta_m >= THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_mid_more_a',
                subject='A',
                category='tone',
                template_key='TONE_DIFF_MID_MORE_A',
                template_params={'delta_db': delta_m},
                evidence_ids=('bands.Mid',),
            ))
        elif delta_m <= -THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_mid_more_b',
                subject='B',
                category='tone',
                template_key='TONE_DIFF_MID_MORE_B',
                template_params={'delta_db': -delta_m},
                evidence_ids=('bands.Mid',),
            ))

    # High band / Tilt
    if 'High' in all_bands:
        delta_h = bands_a['High'] - bands_b['High']
        if delta_h >= THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_high_more_a',
                subject='A',
                category='tone',
                template_key='TONE_DIFF_HIGH_MORE_A',
                template_params={'delta_db': delta_h},
                evidence_ids=('bands.High',),
            ))
        elif delta_h <= -THRESH_TONE_DB:
            claims.append(Claim(
                claim_id='tone_high_more_b',
                subject='B',
                category='tone',
                template_key='TONE_DIFF_HIGH_MORE_B',
                template_params={'delta_db': -delta_h},
                evidence_ids=('bands.High',),
            ))

    # 2. Decay Claims (Strict separation from magnitude)
    if snapshot.d20_low_valid and snapshot.d20_low_a is not None and snapshot.d20_low_b is not None:
        val_a = snapshot.d20_low_a
        val_b = snapshot.d20_low_b
        ref = max(val_a, val_b, 1e-6)
        rel_diff = (val_a - val_b) / ref

        if rel_diff <= -THRESH_D20_RATIO:
            # A is shorter decay (faster)
            claims.append(Claim(
                claim_id='decay_low_faster_a',
                subject='A',
                category='decay',
                template_key='DECAY_LOW_FASTER_A',
                template_params={'d20_a': val_a, 'd20_b': val_b},
                evidence_ids=('d20_low_ms',),
            ))
        elif rel_diff >= THRESH_D20_RATIO:
            # B is shorter decay (A is longer)
            claims.append(Claim(
                claim_id='decay_low_faster_b',
                subject='B',
                category='decay',
                template_key='DECAY_LOW_FASTER_B',
                template_params={'d20_a': val_a, 'd20_b': val_b},
                evidence_ids=('d20_low_ms',),
            ))

    # Boxiness persistence
    if snapshot.boxiness_valid and snapshot.boxiness_excess_a is not None and snapshot.boxiness_excess_b is not None:
        delta_box = snapshot.boxiness_excess_a - snapshot.boxiness_excess_b
        if delta_box >= THRESH_BOXINESS_DB:
            claims.append(Claim(
                claim_id='boxiness_excess_a',
                subject='A',
                category='decay',
                template_key='BOXINESS_EXCESS_A',
                template_params={'delta_db': delta_box},
                evidence_ids=('boxiness_excess_db',),
            ))
        elif delta_box <= -THRESH_BOXINESS_DB:
            claims.append(Claim(
                claim_id='boxiness_excess_b',
                subject='B',
                category='decay',
                template_key='BOXINESS_EXCESS_B',
                template_params={'delta_db': -delta_box},
                evidence_ids=('boxiness_excess_db',),
            ))

    # 3. Transient / Attack Claims
    if snapshot.early_energy_valid and snapshot.early_energy_a is not None and snapshot.early_energy_b is not None:
        val_ea = snapshot.early_energy_a
        val_eb = snapshot.early_energy_b
        ref_e = max(val_ea, val_eb, 1e-6)
        diff_e = (val_ea - val_eb) / ref_e
        if diff_e >= THRESH_ATTACK_RATIO:
            claims.append(Claim(
                claim_id='attack_earlier_a',
                subject='A',
                category='attack',
                template_key='ATTACK_EARLIER_A',
                evidence_ids=('early_energy_5ms',),
            ))
        elif diff_e <= -THRESH_ATTACK_RATIO:
            claims.append(Claim(
                claim_id='attack_earlier_b',
                subject='B',
                category='attack',
                template_key='ATTACK_EARLIER_B',
                evidence_ids=('early_energy_5ms',),
            ))

    # 4. Phase Claims
    if snapshot.gd_valid and snapshot.gd_median_a is not None and snapshot.gd_median_b is not None:
        gd_diff = abs(snapshot.gd_median_a - snapshot.gd_median_b)
        if gd_diff >= 0.5:
            claims.append(Claim(
                claim_id='phase_timing_diff',
                subject='pair',
                category='phase',
                template_key='PHASE_TIMING_DIFF',
                evidence_ids=('gd_median_ms',),
            ))

    # 5. Blend Claims
    if snapshot.blend_valid:
        # B04 convention: positive loss indicates cancellation deficit (e.g. 8.0 dB),
        # or negative if using deficit convention (e.g. -8.0 dB).
        is_cancelling = False
        loss_val = 0.0
        if snapshot.blend_loss_db is not None:
            if snapshot.blend_loss_db <= -3.0:
                is_cancelling = True
                loss_val = abs(snapshot.blend_loss_db)
            elif snapshot.blend_loss_db >= 3.0:
                is_cancelling = True
                loss_val = snapshot.blend_loss_db

        if is_cancelling:
            band_str = snapshot.blend_loss_band.strip() if snapshot.blend_loss_band else ''
            claims.append(Claim(
                claim_id='blend_cancel_warn',
                subject='pair',
                category='blend',
                template_key='BLEND_CANCEL_WARN',
                template_params={'band': band_str or 'บางย่าน',
                                 'loss': loss_val},
                evidence_ids=('blend_loss_db',),
            ))
        else:
            claims.append(Claim(
                claim_id='blend_no_loss',
                subject='pair',
                category='blend',
                template_key='BLEND_NO_LOSS',
                evidence_ids=('blend_loss_db',),
            ))

    return claims


def generate_summary(snapshot: SummarySnapshot, lang: Language = Language.TH) -> MusicianSummary:
    """Pure compiler: transforms snapshot and claims into a MusicianSummary object."""
    mod = phrases_th if lang == Language.TH else phrases_en

    # Handle invalid or unreadable inputs
    limitations: list[str] = list(snapshot.limitations)
    if not snapshot.valid_a:
        limitations.append(mod.LIMIT_INVALID_FILE_A)
    if not snapshot.valid_b:
        limitations.append(mod.LIMIT_INVALID_FILE_B)

    # Check decay limitations if decay was unmeasurable
    if not snapshot.d20_low_valid:
        if snapshot.d20_low_reason:
            limitations.append(snapshot.d20_low_reason)
        elif not limitations:
            limitations.append(mod.LIMIT_NO_DECAY_DATA)

    claims = evaluate_claims(snapshot)

    # Identical case
    if snapshot.identical or any(c.template_key == 'IDENTICAL' for c in claims):
        return MusicianSummary(
            headline=mod.IDENTICAL_OVERVIEW,
            desc_a=mod.IDENTICAL_DESC_A,
            desc_b=mod.IDENTICAL_DESC_B,
            listening_focus=mod.IDENTICAL_FOCUS,
            blend_note=mod.BLEND_NO_LOSS if snapshot.blend_valid else mod.BLEND_NOT_READY,
            limitations=tuple(limitations),
            evidence=tuple(c.claim_id for c in claims),
            lang=lang,
        )

    # 1. Headline / Overview
    tone_claims = [c for c in claims if c.category == 'tone']
    decay_claims = [c for c in claims if c.category == 'decay']
    attack_claims = [c for c in claims if c.category == 'attack']

    overview_parts = []
    if not tone_claims:
        overview_parts.append(mod.TONE_SIMILAR)
    else:
        # Summarize primary tone diff
        primary_tone = tone_claims[0]
        text = getattr(mod, primary_tone.template_key, '')
        if text:
            overview_parts.append(text)

    if not decay_claims:
        if snapshot.d20_low_valid:
            overview_parts.append(mod.DECAY_SIMILAR)
    else:
        primary_decay = decay_claims[0]
        text = getattr(mod, primary_decay.template_key, '')
        if text:
            overview_parts.append(text)

    headline = " แต่ ".join(overview_parts) if lang == Language.TH else "; ".join(overview_parts)
    if not headline:
        headline = mod.IDENTICAL_OVERVIEW

    # 2. Descriptions for A and B
    a_points = []
    b_points = []

    for c in claims:
        text = getattr(mod, c.template_key, '')
        if not text:
            continue
        if '{' in text and c.template_params:
            try:
                text = text.format(**c.template_params)
            except Exception:
                pass

        if c.subject == 'A':
            a_points.append(text)
        elif c.subject == 'B':
            b_points.append(text)

    if not a_points:
        desc_a = mod.IDENTICAL_DESC_A
    else:
        desc_a = " และ ".join(a_points) if lang == Language.TH else "; ".join(a_points)

    if not b_points:
        desc_b = mod.IDENTICAL_DESC_B
    else:
        desc_b = " และ ".join(b_points) if lang == Language.TH else "; ".join(b_points)

    # 3. Listening focus (Max 3 items)
    focus_items: list[str] = []

    # If decay differs, advise checking palm mutes
    if any(c.claim_id.startswith('decay_low') for c in claims):
        focus_items.append(mod.FOCUS_PALM_MUTE_DECAY)

    # If attack differs, advise checking pick attack
    if attack_claims:
        focus_items.append(mod.FOCUS_PICK_ATTACK)

    # If tone differs, advise low weight or high openness
    if any(c.claim_id.startswith('tone_low_more') for c in claims):
        focus_items.append(mod.FOCUS_LOW_WEIGHT)
    elif any(c.claim_id.startswith('tone_high_more') for c in claims):
        focus_items.append(mod.FOCUS_HIGH_OPENNESS)

    # If boxiness differs
    if any(c.claim_id.startswith('boxiness') for c in claims):
        focus_items.append(mod.FOCUS_BOXINESS)

    # Fallback to general advice if empty
    if not focus_items:
        focus_items.extend(mod.IDENTICAL_FOCUS)

    listening_focus = tuple(focus_items[:3])

    # 4. Blend note
    blend_note = ''
    blend_claims = [c for c in claims if c.category == 'blend']
    if blend_claims:
        bc = blend_claims[0]
        tmpl = getattr(mod, bc.template_key, '')
        if tmpl and bc.template_params:
            try:
                blend_note = tmpl.format(**bc.template_params)
            except Exception:
                blend_note = tmpl
        else:
            blend_note = tmpl
    else:
        blend_note = mod.BLEND_NOT_READY

    return MusicianSummary(
        headline=headline,
        desc_a=desc_a,
        desc_b=desc_b,
        listening_focus=listening_focus,
        blend_note=blend_note,
        limitations=tuple(limitations),
        evidence=tuple(c.claim_id for c in claims),
        lang=lang,
    )
