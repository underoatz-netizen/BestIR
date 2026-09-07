"""Contracts and data models for Musician Summary (docs/MUSICIAN_SUMMARY_SPEC_TH.md).

Pure data structures. No DSP, no Qt, no network dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Language(str, Enum):
    TH = 'th'
    EN = 'en'


@dataclass(frozen=True)
class Claim:
    """A single evidenced finding comparing IR A and B."""
    claim_id: str
    subject: str                  # 'A', 'B', 'pair', or 'both'
    category: str                 # 'tone', 'decay', 'attack', 'phase', 'blend', 'identity'
    template_key: str
    template_params: dict = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    interpretation_level: str = 'acoustic'   # 'acoustic', 'character', 'guidance'
    validity_reason: str = ''


@dataclass(frozen=True)
class MusicianSummary:
    """Structured summary output suitable for rendering and export."""
    headline: str
    desc_a: str
    desc_b: str
    listening_focus: tuple[str, ...] = ()    # max 3 items
    blend_note: str = ''
    limitations: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    lang: Language = Language.TH

    def formatted_text(self) -> str:
        """Render the complete musician summary as readable multi-line prose."""
        sections = []
        if self.lang == Language.TH:
            if self.headline:
                sections.append(f"ภาพรวม:\n{self.headline}")
            if self.desc_a:
                sections.append(f"IR A:\n{self.desc_a}")
            if self.desc_b:
                sections.append(f"IR B:\n{self.desc_b}")
            if self.listening_focus:
                focus_lines = "\n".join(f"• {item}" for item in self.listening_focus)
                sections.append(f"จุดต่างที่ควรลองฟัง:\n{focus_lines}")
            if self.blend_note:
                sections.append(f"การผสม (Blend):\n{self.blend_note}")
            if self.limitations:
                lim_lines = "\n".join(f"• {lim}" for lim in self.limitations)
                sections.append(f"ข้อจำกัดของข้อมูล:\n{lim_lines}")
            sections.append("สรุปจากข้อมูล IR เพื่อช่วยเลือกลองฟัง ไม่ใช่ผลการฟังจริงผ่านชุดเสียงของคุณ")
        else:
            if self.headline:
                sections.append(f"Overview:\n{self.headline}")
            if self.desc_a:
                sections.append(f"IR A:\n{self.desc_a}")
            if self.desc_b:
                sections.append(f"IR B:\n{self.desc_b}")
            if self.listening_focus:
                focus_lines = "\n".join(f"• {item}" for item in self.listening_focus)
                sections.append(f"Listening Focus:\n{focus_lines}")
            if self.blend_note:
                sections.append(f"Blend Note:\n{self.blend_note}")
            if self.limitations:
                lim_lines = "\n".join(f"• {lim}" for lim in self.limitations)
                sections.append(f"Data Limitations:\n{lim_lines}")
            sections.append("Summary derived from IR measurements to guide auditioning; not a claim of actual listening experience through your setup.")
        return "\n\n".join(sections)


@dataclass(frozen=True)
class SummarySnapshot:
    """Immutable input snapshot capturing validated features for pair comparison."""
    # Identification
    name_a: str = 'A'
    name_b: str = 'B'
    valid_a: bool = True
    valid_b: bool = True
    identical: bool = False

    # Tone balance (dB relative or absolute band levels)
    # Band levels relative to overall mean or curve
    bands_a: dict[str, float] = field(default_factory=dict)
    bands_b: dict[str, float] = field(default_factory=dict)
    tilt_a: float | None = None
    tilt_b: float | None = None
    flatness_a: float | None = None
    flatness_b: float | None = None

    # Temporal / Decay features (with validity)
    d20_low_a: float | None = None
    d20_low_b: float | None = None
    d20_low_valid: bool = False
    d20_low_reason: str = ''

    boxiness_excess_a: float | None = None
    boxiness_excess_b: float | None = None
    boxiness_valid: bool = False
    boxiness_ridge_hz: float | None = None

    # Transient / Attack features
    time_to_peak_a: float | None = None
    time_to_peak_b: float | None = None
    time_to_peak_valid: bool = False

    early_energy_a: float | None = None
    early_energy_b: float | None = None
    early_energy_valid: bool = False

    centroid_a: float | None = None
    centroid_b: float | None = None
    centroid_valid: bool = False

    crest_factor_a: float | None = None
    crest_factor_b: float | None = None
    crest_factor_valid: bool = False

    # Phase / Group delay
    gd_median_a: float | None = None
    gd_median_b: float | None = None
    gd_valid: bool = False

    # Blend / Pair comparison (optional)
    pair_status: str = ''
    blend_loss_db: float | None = None
    blend_loss_band: str = ''
    blend_valid: bool = False
    blend_ratio: float = 0.5
    alignment_ms: float = 0.0

    # System / diagnostic limitations
    limitations: tuple[str, ...] = ()
