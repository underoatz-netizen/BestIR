"""Musician Summary module.

Provides evidenced, non-technical musician-friendly summary descriptions
for IR comparison in Thai and English (docs/MUSICIAN_SUMMARY_SPEC_TH.md).
"""
from __future__ import annotations

from typing import Any, Optional

from .contracts import Claim, Language, MusicianSummary, SummarySnapshot
from .adapter import make_snapshot_from_fingerprints
from .rules import generate_summary, evaluate_claims
from ..contracts import ResponseFingerprint


def describe_pair(
    fp_a: Optional[ResponseFingerprint],
    fp_b: Optional[ResponseFingerprint],
    name_a: str = 'A',
    name_b: str = 'B',
    bands_a: Optional[dict[str, float]] = None,
    bands_b: Optional[dict[str, float]] = None,
    pair_res: Optional[Any] = None,
    blend_res: Optional[Any] = None,
    lang: Language = Language.TH,
    snapshot: Optional[SummarySnapshot] = None,
) -> MusicianSummary:
    """Entry point for describing a pair of IRs in musician-friendly terms."""
    if snapshot is None:
        snapshot = make_snapshot_from_fingerprints(
            fp_a=fp_a,
            fp_b=fp_b,
            name_a=name_a,
            name_b=name_b,
            bands_a=bands_a,
            bands_b=bands_b,
            pair_res=pair_res,
            blend_res=blend_res,
        )
    return generate_summary(snapshot, lang=lang)


__all__ = [
    'describe_pair',
    'SummarySnapshot',
    'Claim',
    'MusicianSummary',
    'Language',
    'make_snapshot_from_fingerprints',
    'generate_summary',
    'evaluate_claims',
]
