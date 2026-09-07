"""Thai phrase templates and dictionary for Musician Summary.

Strict adherence to docs/MUSICIAN_SUMMARY_SPEC_TH.md:
- Tone (magnitude) and Temporal Response (decay/attack) are strictly separated.
- No winner bias or psychoacoustic overclaims.
- Clear evidence-to-character phrasing.
"""
from __future__ import annotations

# Identical
IDENTICAL_OVERVIEW = "จากค่าที่วัด คู่นี้มีโทนและการตอบสนองใกล้เคียงกันมาก ยังไม่พบความต่างเด่นชัด"
IDENTICAL_DESC_A = "โทนและการเก็บตัวใกล้เคียงกับ B"
IDENTICAL_DESC_B = "โทนและการเก็บตัวใกล้เคียงกับ A"
IDENTICAL_FOCUS = (
    "ลองสลับฟัง A/B ด้วย DI เดียวกันและตั้งระดับเสียงให้เท่ากัน (Level Match) เพื่อฟังรายละเอียดปลีกย่อย",
)

# Tone differences
TONE_SIMILAR = "โทนรวมใกล้เคียงกัน"
TONE_DIFF_LOW_MORE_A = "A มีน้ำหนักย่านต่ำมากกว่า B"
TONE_DIFF_LOW_MORE_B = "B มีน้ำหนักย่านต่ำมากกว่า A"
TONE_DIFF_LOWMID_MORE_A = "A มีย่านกลางต่ำมากกว่า ให้แนวโน้มโทนหนากว่า"
TONE_DIFF_LOWMID_MORE_B = "B มีย่านกลางต่ำมากกว่า ให้แนวโน้มโทนหนากว่า"
TONE_DIFF_MID_MORE_A = "A ย่านกลางเด่นกว่า"
TONE_DIFF_MID_MORE_B = "B ย่านกลางเด่นกว่า"
TONE_DIFF_HIGH_MORE_A = "A ปลายเสียงเปิดและสว่างกว่า B"
TONE_DIFF_HIGH_MORE_B = "B ปลายเสียงเปิดและสว่างกว่า A"

# Decay differences
DECAY_SIMILAR = "การเก็บตัวของหางเสียงใกล้เคียงกัน"
DECAY_LOW_FASTER_A = "A ย่านต่ำเก็บตัวเร็วกว่า (หางย่านต่ำสั้นกว่า B)"
DECAY_LOW_FASTER_B = "B ย่านต่ำเก็บตัวเร็วกว่า (หางย่านต่ำสั้นกว่า A)"
DECAY_LOW_LONGER_A = "A ย่านต่ำค้างนานกว่า B"
DECAY_LOW_LONGER_B = "B ย่านต่ำค้างนานกว่า A"
BOXINESS_EXCESS_A = "A มีกลางต่ำบางช่วงค้างเด่นกว่า อาจฟังอู้หรือเป็นกล่องในบางริฟฟ์"
BOXINESS_EXCESS_B = "B มีกลางต่ำบางช่วงค้างเด่นกว่า อาจฟังอู้หรือเป็นกล่องในบางริฟฟ์"

# Attack / Transient differences
ATTACK_EARLIER_A = "A มีพลังงานกระจุกที่ต้นเสียงมากกว่า มีแนวโน้มให้หัวโน้ตเด่นกว่า"
ATTACK_EARLIER_B = "B มีพลังงานกระจุกที่ต้นเสียงมากกว่า มีแนวโน้มให้หัวโน้ตเด่นกว่า"

# Phase / Group delay
PHASE_TIMING_DIFF = "บางย่านความถี่มีเวลาตอบสนองต่างกัน"

# Blend
BLEND_NO_LOSS = "เมื่อผสม 50/50 ยังไม่พบการหักล้างของย่านความถี่อย่างมีนัยสำคัญ"
BLEND_CANCEL_WARN = "เมื่อผสม 50/50 ย่าน {band} ลดลง {loss:.1f} dB จากการหักล้างของเฟส"
BLEND_NOT_READY = "ยังไม่สรุปการผสม ต้องผ่านการตรวจผลการผสมของคู่นี้ก่อน"

# Listening focus recommendations
FOCUS_PALM_MUTE_DECAY = "ใช้ DI เดียวกันและ level match สลับฟังที่ช่วง palm mute ตามด้วยหยุดสาย สังเกตหางย่านต่ำหลังหยุดโน้ต"
FOCUS_PICK_ATTACK = "สลับฟังหัวโน้ตจังหวะดีดลงสายแรก เพื่อเปรียบเทียบความคมชัดของ transient"
FOCUS_LOW_WEIGHT = "ลองฟังเสียงคอร์ดเต็มและโน้ตสายลึก เพื่อเปรียบเทียบน้ำหนักและความแน่นของเนื้อเสียงย่านต่ำ"
FOCUS_HIGH_OPENNESS = "ลองฟังเสียงแหลมและความกังวานของปลายเสียง เพื่อดูว่าเปิดโปร่งหรือนุ่มนวลกว่า"
FOCUS_BOXINESS = "ลองฟังย่านกลางต่ำว่าเติมเนื้อเสียงให้อิ่ม หรือทำให้เสียงริฟฟ์ฟังอู้ในมิกซ์ของคุณ"

# Limitations / Edge cases
LIMIT_B_TOO_SHORT_DECAY = "โทนเปรียบเทียบได้ แต่ไฟล์ B สั้นเกินไปสำหรับประเมินหางย่านต่ำ"
LIMIT_A_TOO_SHORT_DECAY = "โทนเปรียบเทียบได้ แต่ไฟล์ A สั้นเกินไปสำหรับประเมินหางย่านต่ำ"
LIMIT_NO_DECAY_DATA = "ไม่มีข้อมูลการสลายตัว (Decay) ที่สมบูรณ์เพียงพอสำหรับการวิเคราะห์หางเสียง"
LIMIT_INVALID_FILE_A = "ไฟล์ A ไม่สามารถอ่านหรือประเมินค่าทางเสียงได้อย่างสมบูรณ์"
LIMIT_INVALID_FILE_B = "ไฟล์ B ไม่สามารถอ่านหรือประเมินค่าทางเสียงได้อย่างสมบูรณ์"
LIMIT_NO_PAIR_ANALYSIS = "ยังไม่ได้ประเมินความเข้ากันได้ของการผสม (Blend)"
