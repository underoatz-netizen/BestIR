import pytest
from app.extensions.musician_summary.contracts import Language, SummarySnapshot, Claim, MusicianSummary
from app.extensions.musician_summary.rules import generate_summary, evaluate_claims
from app.extensions.musician_summary import describe_pair


def test_identical_irs_summary():
    snapshot = SummarySnapshot(
        name_a='IR1',
        name_b='IR1',
        identical=True,
    )
    # Thai
    summary_th = generate_summary(snapshot, lang=Language.TH)
    assert "ใกล้เคียงกัน" in summary_th.headline
    assert "ใกล้เคียง" in summary_th.desc_a
    assert "ใกล้เคียง" in summary_th.desc_b

    # English
    summary_en = generate_summary(snapshot, lang=Language.EN)
    assert "very similar" in summary_en.headline.lower() or "close" in summary_en.headline.lower()
    assert "close" in summary_en.desc_a.lower()
    assert "close" in summary_en.desc_b.lower()


def test_tone_vs_decay_separation():
    """Test that low magnitude (weight) and decay time are strictly separated.
    
    A has higher low magnitude (+3 dB) but shorter decay (faster tail).
    Prose must say A has more low weight BUT decays faster, never confusing the two.
    """
    snapshot = SummarySnapshot(
        name_a='IR_A',
        name_b='IR_B',
        bands_a={'Low': 3.0, 'Mid': 0.0, 'High': 0.0},
        bands_b={'Low': 0.0, 'Mid': 0.0, 'High': 0.0},
        d20_low_a=20.0,
        d20_low_b=40.0,
        d20_low_valid=True,
    )

    summary_th = generate_summary(snapshot, lang=Language.TH)
    # A has more low weight
    assert "A มีน้ำหนักย่านต่ำมากกว่า B" in summary_th.desc_a or "น้ำหนักย่านต่ำมากกว่า" in summary_th.headline
    # A decays faster
    assert "A ย่านต่ำเก็บตัวเร็วกว่า" in summary_th.desc_a or "เก็บตัวเร็วกว่า" in summary_th.headline

    summary_en = generate_summary(snapshot, lang=Language.EN)
    assert "low-end weight" in summary_en.formatted_text()
    assert "decays faster" in summary_en.formatted_text() or "shorter low-end tail" in summary_en.formatted_text()


def test_swap_ab_symmetry():
    """Swapping A and B should invert subjects cleanly without bias."""
    snap_ab = SummarySnapshot(
        name_a='A',
        name_b='B',
        bands_a={'High': 2.5},
        bands_b={'High': 0.0},
        d20_low_a=50.0,
        d20_low_b=20.0,
        d20_low_valid=True,
    )
    snap_ba = SummarySnapshot(
        name_a='B',
        name_b='A',
        bands_a={'High': 0.0},
        bands_b={'High': 2.5},
        d20_low_a=20.0,
        d20_low_b=50.0,
        d20_low_valid=True,
    )

    sum_ab = generate_summary(snap_ab, lang=Language.TH)
    sum_ba = generate_summary(snap_ba, lang=Language.TH)

    # In AB, A has more high, and A decays longer (B decays faster)
    assert "A ปลายเสียงเปิดและสว่างกว่า B" in sum_ab.desc_a
    assert "B ย่านต่ำเก็บตัวเร็วกว่า" in sum_ab.desc_b or "B ย่านต่ำเก็บตัวเร็วกว่า" in sum_ab.desc_a

    # In BA, B has more high, and A decays faster
    assert "B ปลายเสียงเปิดและสว่างกว่า A" in sum_ba.desc_b
    assert "A ย่านต่ำเก็บตัวเร็วกว่า" in sum_ba.desc_a or "A ย่านต่ำเก็บตัวเร็วกว่า" in sum_ba.desc_b


def test_language_switch():
    snapshot = SummarySnapshot(
        name_a='IR_A',
        name_b='IR_B',
        bands_a={'Mid': 2.0},
        bands_b={'Mid': 0.0},
    )
    th = generate_summary(snapshot, lang=Language.TH)
    en = generate_summary(snapshot, lang=Language.EN)

    assert "ภาพรวม:" in th.formatted_text()
    assert "Overview:" in en.formatted_text()
    assert "ย่านกลางเด่นกว่า" in th.formatted_text()
    assert "prominent midrange" in en.formatted_text()


def test_invalid_and_partial_data_shows_limitations():
    snapshot = SummarySnapshot(
        name_a='IR_A',
        name_b='IR_B',
        bands_a={'Low': 0.0},
        bands_b={'Low': 0.0},
        d20_low_valid=False,
        d20_low_reason="B is too short (length < 20 ms) to evaluate low-end decay",
    )
    summary = generate_summary(snapshot, lang=Language.TH)
    assert len(summary.limitations) > 0
    assert any("B is too short" in lim or "สั้นเกินไป" in lim or "ไม่มีข้อมูลการสลายตัว" in lim for lim in summary.limitations)


def test_no_crash_on_empty_or_edge_cases():
    empty_snap = SummarySnapshot()
    summary = generate_summary(empty_snap, lang=Language.TH)
    assert summary is not None
    assert isinstance(summary.formatted_text(), str)
    assert len(summary.formatted_text()) > 0
