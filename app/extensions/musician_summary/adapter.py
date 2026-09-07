"""Adapter transforming raw/extension results into an immutable SummarySnapshot.

Pure read-only conversion. No side effects, no mutation.
"""
from __future__ import annotations

from typing import Any, Optional

from .contracts import SummarySnapshot
from ..contracts import ResponseFingerprint, AnalysisStatus


def make_snapshot_from_fingerprints(
    fp_a: Optional[ResponseFingerprint],
    fp_b: Optional[ResponseFingerprint],
    name_a: str = 'A',
    name_b: str = 'B',
    bands_a: Optional[dict[str, float]] = None,
    bands_b: Optional[dict[str, float]] = None,
    pair_res: Optional[Any] = None,
    blend_res: Optional[Any] = None,
) -> SummarySnapshot:
    """Construct a SummarySnapshot from available fingerprints, analysis records, and pair results."""
    valid_a = fp_a is not None
    valid_b = fp_b is not None

    feats_a = fp_a.all_features() if fp_a else {}
    feats_b = fp_b.all_features() if fp_b else {}

    # Decay
    d20_a_obj = feats_a.get('d20_low_ms')
    d20_b_obj = feats_b.get('d20_low_ms')
    d20_low_a = d20_a_obj.value if d20_a_obj and d20_a_obj.valid else None
    d20_low_b = d20_b_obj.value if d20_b_obj and d20_b_obj.valid else None
    d20_valid = (d20_low_a is not None and d20_low_b is not None)
    d20_reason = ''
    if not d20_valid:
        if d20_b_obj and not d20_b_obj.valid:
            d20_reason = d20_b_obj.note or 'B is too short or noisy for low-end decay measurement'
        elif d20_a_obj and not d20_a_obj.valid:
            d20_reason = d20_a_obj.note or 'A is too short or noisy for low-end decay measurement'

    # Boxiness
    box_a_obj = feats_a.get('boxiness_persistence_excess_db')
    box_b_obj = feats_b.get('boxiness_persistence_excess_db')
    box_excess_a = box_a_obj.value if box_a_obj and box_a_obj.valid else None
    box_excess_b = box_b_obj.value if box_b_obj and box_b_obj.valid else None
    box_valid = (box_excess_a is not None and box_excess_b is not None)

    # Attack / Transient
    ttp_a_obj = feats_a.get('time_to_peak_ms')
    ttp_b_obj = feats_b.get('time_to_peak_ms')
    ttp_a = ttp_a_obj.value if ttp_a_obj and ttp_a_obj.valid else None
    ttp_b = ttp_b_obj.value if ttp_b_obj and ttp_b_obj.valid else None
    ttp_valid = (ttp_a is not None and ttp_b is not None)

    ee_a_obj = feats_a.get('early_energy_5ms')
    ee_b_obj = feats_b.get('early_energy_5ms')
    ee_a = ee_a_obj.value if ee_a_obj and ee_a_obj.valid else None
    ee_b = ee_b_obj.value if ee_b_obj and ee_b_obj.valid else None
    ee_valid = (ee_a is not None and ee_b is not None)

    cen_a_obj = feats_a.get('centroid_ms')
    cen_b_obj = feats_b.get('centroid_ms')
    cen_a = cen_a_obj.value if cen_a_obj and cen_a_obj.valid else None
    cen_b = cen_b_obj.value if cen_b_obj and cen_b_obj.valid else None
    cen_valid = (cen_a is not None and cen_b is not None)

    cf_a_obj = feats_a.get('crest_factor')
    cf_b_obj = feats_b.get('crest_factor')
    cf_a = cf_a_obj.value if cf_a_obj and cf_a_obj.valid else None
    cf_b = cf_b_obj.value if cf_b_obj and cf_b_obj.valid else None
    cf_valid = (cf_a is not None and cf_b is not None)

    # Phase
    gd_a_obj = feats_a.get('gd_median_ms')
    gd_b_obj = feats_b.get('gd_median_ms')
    gd_a = gd_a_obj.value if gd_a_obj and gd_a_obj.valid else None
    gd_b = gd_b_obj.value if gd_b_obj and gd_b_obj.valid else None
    gd_valid = (gd_a is not None and gd_b is not None)

    # Blend / Pair
    blend_valid = False
    blend_loss_db = None
    blend_loss_band = ''
    blend_ratio = 0.5
    alignment_ms = 0.0
    if blend_res is not None:
        st = getattr(blend_res, 'status', None)
        if st == AnalysisStatus.OK or str(st).lower().endswith('ok'):
            blend_valid = True
            blend_loss_db = getattr(blend_res, 'worst_notch_depth_db', None)
            blend_loss_band = getattr(blend_res, 'worst_notch_band', '')
            blend_ratio = getattr(blend_res, 'ratio', 0.5)

    # Check identical
    is_identical = False
    if fp_a is not None and fp_b is not None:
        if fp_a.key == fp_b.key and fp_a.key.sha256:
            is_identical = True

    return SummarySnapshot(
        name_a=name_a,
        name_b=name_b,
        valid_a=valid_a,
        valid_b=valid_b,
        identical=is_identical,
        bands_a=bands_a or {},
        bands_b=bands_b or {},
        d20_low_a=d20_low_a,
        d20_low_b=d20_low_b,
        d20_low_valid=d20_valid,
        d20_low_reason=d20_reason,
        boxiness_excess_a=box_excess_a,
        boxiness_excess_b=box_excess_b,
        boxiness_valid=box_valid,
        time_to_peak_a=ttp_a,
        time_to_peak_b=ttp_b,
        time_to_peak_valid=ttp_valid,
        early_energy_a=ee_a,
        early_energy_b=ee_b,
        early_energy_valid=ee_valid,
        centroid_a=cen_a,
        centroid_b=cen_b,
        centroid_valid=cen_valid,
        crest_factor_a=cf_a,
        crest_factor_b=cf_b,
        crest_factor_valid=cf_valid,
        gd_median_a=gd_a,
        gd_median_b=gd_b,
        gd_valid=gd_valid,
        blend_valid=blend_valid,
        blend_loss_db=blend_loss_db,
        blend_loss_band=blend_loss_band,
        blend_ratio=blend_ratio,
        alignment_ms=alignment_ms,
    )
