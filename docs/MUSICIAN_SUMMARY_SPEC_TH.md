# BestIR — สรุป A/B เป็นภาษานักดนตรี

สถานะ: **ข้อกำหนดเพิ่มเติมสำหรับส่งต่อ AI coder — ยังไม่ได้ติดตั้งลง UI**

วันที่: 2026-08-31

เป้าหมาย: นักดนตรีอ่าน Summary แล้วเข้าใจว่า IR A และ B มีโทนและการตอบสนองอย่างไร ต่างกันตรงไหน และควรลองฟังอะไรต่อ โดยไม่ต้องอ่านค่า DSP ทุกช่องเอง

ใช้ skill `design:ux-copy` วางภาษาและลำดับการอ่าน: ชัดเจน กระชับ เป็นธรรมชาติ และเปิดเผยรายละเอียดเมื่อผู้ใช้ต้องการ ไม่พบ skill แปล DSP เป็นภาษานักดนตรีโดยตรงในรายการที่ติดตั้ง จึงไม่อ้างว่ามีตัวแปลเฉพาะทางหรือได้ติดตั้ง skill ใหม่

## 1. สิ่งที่ต้องเพิ่มใน Summary

ชื่อส่วน: **สรุปสำหรับนักดนตรี**

แสดงข้อมูลตามลำดับนี้:

1. **ภาพรวมคู่นี้** — โทนใกล้กันหรือต่างกันอย่างไร และความต่างเด่นอยู่ที่โทนหรือลักษณะการสลายตัว
2. **IR A / IR B** — คนละ 1–2 ประโยค อธิบายโทนและการตอบสนองที่มีหลักฐาน
3. **จุดต่างที่ควรลองฟัง** — ไม่เกิน 3 ข้อ เช่น หัวโน้ต หางย่านต่ำ หรือกลางต่ำที่ค้างเด่น
4. **เมื่อผสมกัน** — แสดงเฉพาะเมื่อ pair/blend analysis ผ่าน validation พร้อม ratio, alignment และ channel ที่ใช้; ถ้าไม่พร้อมให้บอกเหตุผล
5. **ดูเหตุผลและค่าที่วัด** — เปิด evidence ของแต่ละข้อความ รวม units, bands, windows, source identity และข้อจำกัด โดยยังเข้าถึงตารางเดิมได้

บรรทัดท้าย: “สรุปจากข้อมูล IR เพื่อช่วยเลือกลองฟัง ไม่ใช่ผลการฟังจริงผ่านชุดเสียงของคุณ”

ใช้ไทยเป็นหลักและคงคำที่นักดนตรีคุ้น เช่น IR, attack, palm mute, blend; tooltip ให้ชื่อ DSP เต็ม ไม่แปลทับศัพท์ทุกคำจนอ่านยาก

## 2. ตัวอย่างข้อความที่ต้องการ

**ตัวอย่างสมมติของรูปแบบภาษา ไม่ใช่ผลวิเคราะห์ IR คู่ปัจจุบัน** สมมติว่าตรวจยืนยันแล้วว่าโทนใกล้กัน, A มี low-band decay สั้นกว่า และ B มี low-mid persistence สูงกว่า:

> **ภาพรวม:** โทนรวมใกล้กัน แต่ต่างกันที่หางเสียง: A ย่านต่ำเก็บตัวเร็วกว่า ส่วน B มีย่านกลางต่ำค้างเด่นกว่า
>
> **IR A:** ปริมาณเบสใกล้กับ B แต่หางย่านต่ำสั้นกว่า ถ้ามองหาเสียงที่เก็บตัวไว ลองเริ่มฟังจาก A
>
> **IR B:** เบสไม่ได้มากกว่าชัดเจน แต่กลางต่ำค้างเด่นกว่า ลองฟังว่าลักษณะนี้ช่วยเติมเนื้อเสียง หรือทำให้ริฟฟ์ของคุณฟังอู้ขึ้น
>
> **ลองฟัง:** ใช้ DI เดียวกันและ level match แล้วสลับ A/B ที่ช่วง palm mute ตามด้วยหยุดสาย ฟังหางย่านต่ำและกลางต่ำหลังหยุดโน้ต
>
> **การ blend:** ยังไม่สรุป ต้องตรวจผลการผสมของคู่นี้ก่อน

หากต้นเสียงต่างกันโดยมีหลาย metric สนับสนุน ใช้ “A มีพลังงานกระจุกที่ต้นเสียงมากกว่า” หรือ “A มีแนวโน้มให้หัวโน้ตเด่นกว่า” ไม่ใช้ “A เร็วกว่า 2 ms จึงเล่นติดมือกว่า”

หากต่างน้อย: “จากค่าที่วัด คู่นี้ยังไม่พบความต่างเด่นในโทนและการเก็บตัว ลองสลับฟังด้วยระดับเสียงเท่ากันเพื่อเลือกตัวที่ชอบ” ห้ามแต่ง character ให้ต่างเพียงเพราะเป็นคนละไฟล์

หากข้อมูลบางส่วนไม่พอ: “โทนเปรียบเทียบได้ แต่ไฟล์ B สั้นเกินไปสำหรับประเมินหางย่านต่ำ จึงยังสรุปไม่ได้ว่าตัวไหนเก็บตัวเร็วกว่า”

## 3. พจนานุกรม DSP → ภาษานักดนตรี

คำต่อไปนี้เป็น **interpretation rules สำหรับออกแบบและทดสอบ** ไม่ใช่กฎ psychoacoustic ที่รับรองกับทุกกีตาร์ ทุกคน และทุก signal chain

| หลักฐาน | ข้อความที่อนุญาตเมื่อผ่านเกณฑ์ | สิ่งที่ต้องไม่สรุปจากค่านั้นลำพัง |
|---|---|---|
| Relative low-band magnitude มากกว่า บน reference/normalization เดียวกัน | “A มีน้ำหนักย่านต่ำมากกว่า B” | เก็บตัวช้า, palm mute ไม่กระชับ |
| Broad low-mid balance มากกว่าอย่างสม่ำเสมอ | “A มีย่านกลางต่ำมากกว่า ให้แนวโน้มโทนหนากว่า” | มี resonance/boxiness แน่นอน |
| Broad high-band balance มากกว่า ไม่ใช่แค่ isolated bin | “A ปลายเสียงเปิดกว่า / B ปลายเสียงนุ่มกว่าเมื่อเทียบกัน” | ฟังดีกว่า, มีรายละเอียดจริงมากกว่า, บาดหูแน่นอน |
| Midrange balance ต่างจาก bands ข้างเคียงบน reference ที่ระบุ | “A กลางเด่นกว่า” หรือ “B เว้ากลางกว่า” | ตัดมิกซ์ดีกว่าเสมอ, ระบุแบรนด์ตู้/ไมค์จากกราฟ |
| Low-band D20 สั้นกว่า และ window/length/noise/truncation checks ผ่าน | “ย่านต่ำเก็บตัวเร็วกว่า / หางย่านต่ำสั้นกว่า” | เบสน้อยกว่า, ดีกว่าสำหรับทุกริฟฟ์ |
| Low-band D20 ยาวกว่าโดย valid ทั้งคู่ | “ย่านต่ำค้างนานกว่า” | sustain ของสายยาวขึ้นเท่าค่าที่วัด, เป็น room RT60 |
| Early-energy, energy centroid และ onset-relative envelope timing สนับสนุนกัน | “พลังงานกระจุกที่ต้นเสียงมากกว่า”; อาจขยายเป็น “มีแนวโน้มให้หัวโน้ตเด่นกว่า” | ความไวต่อแรงปิ๊ก, compression, sag หรือ latency ทั้งระบบ |
| Localized low-mid excess persistence เทียบ neighboring bands พร้อม valid ridge/duration | “กลางต่ำบางช่วงค้างเด่นกว่า อาจฟังอู้หรือเป็นกล่องในบางเสียง” | ย่านกลางต่ำมาก = boxy, ระบุ boxiness จาก EQ อย่างเดียว |
| Correct per-channel phase/GD พร้อม time-origin และ mask ที่เหมือนกัน | technical detail: “บางย่านมีเวลาตอบสนองต่างกัน” | GD มาก = เล่นหน่วง, GD ต่ำ = ผสมกันดีเสมอ |
| Verified pair complex sum ที่ ratio/alignment ปัจจุบัน | “เมื่อผสม 50/50 ย่าน … ลดลงจากการหักล้าง”; ถ้าไม่มี notable loss ให้ “ยังไม่พบการหักล้างเด่นในช่วงที่ตรวจ” | “คู่นี้เข้ากัน 100%”, “ผสมแล้วหนาขึ้นแน่นอน”, ความเข้ากันจาก phase curve รูปร่างคล้ายกันเท่านั้น |
| ความต่างต่ำกว่า reporting threshold ที่ผ่าน calibration | “ใกล้เคียงกันในด้าน …” | “เสียงเหมือนกันแน่นอน” หรือ “ไม่มีใครได้ยินความต่าง” |

**ต้องแยกเสมอ:** ปริมาณเบส ≠ ระยะหางเบส; prominence ของหัวโน้ต ≠ audio interface latency; IR linear response ≠ amp dynamics; pair compatibility ≠ ความชอบส่วนบุคคล

การออกแบบคำอธิบายต้องเคารพ window/time-origin: window shape มีผลต่อภาพ decay และ CSD ช่วงท้ายมี frequency resolution ลดลงตามความยาวหน้าต่างที่เหลือ จึงห้ามเอาหางที่วัดไม่ได้มาแปลว่า “กระชับ”. [REW Waterfall documentation](https://www.roomeqwizard.com/help/help_en-GB/html/graph_waterfall.html)

Group delay และ phase เปลี่ยนตาม time-zero และการตั้ง window จึงต้องเก็บ provenance ก่อนนำไปพูดถึงความต่างด้านเวลา. [REW Group Delay documentation](https://www.roomeqwizard.com/help/help_en-GB/html/graph_groupdelay.html)

## 4. แหล่งข้อมูลและจุดต่อกับโค้ดเดิม

สภาพโค้ดปัจจุบัน:

- [SummaryPanel.show_fingerprints](E:/Projects/BestIR/app/extensions/ui/summary_panel.py:118) รับเฉพาะ response fingerprints กับชื่อไฟล์ จึงยังไม่มีข้อมูล tone curve สำหรับสรุปโทนครบ
- [ResponseFingerprint](E:/Projects/BestIR/app/extensions/contracts.py:344) มี transient/decay/phase และ validity แต่ไม่ได้มี tonal balance
- [AnalysisResult](E:/Projects/BestIR/app/core/analysis.py:41) มี `curve_db`, `band_levels`, `tilt_db_oct` ที่อ่านได้ผ่าน adapter โดยไม่แก้ record
- `SummaryPanel.why` ปัจจุบันเรียง raw delta ต่าง units แล้วแสดง “higher by ...” ห้ามแปลข้อความเดิมตรง ๆ เพราะอาจรับ unit bug/ordering bias มาด้วย ต้องเริ่มจาก validated values

เสนอเป็น extension ใหม่ โดยยังไม่เปลี่ยน public signatures/state ของ legacy:

```text
read-only legacy records + validated response/pair results
    → MusicianSummaryAdapter (validate identities, units, analysis context)
    → describe_pair() (pure evidence-to-claims rules)
    → Thai phrase templates
    → MusicianSummaryView (พร้อมปุ่มดูหลักฐาน)
```

ไฟล์ที่เสนอสร้าง:

- `app/extensions/musician_summary/contracts.py` — frozen input/claim/summary types แยกจาก existing contracts
- `app/extensions/musician_summary/adapter.py` — copy เฉพาะ scalar/context ที่จำเป็น; arrays อ่านอย่างเดียว
- `app/extensions/musician_summary/rules.py` — pure functions, ไม่มี Qt/audio I/O/การเรียก DSP ซ้ำ
- `app/extensions/musician_summary/phrases_th.py` — glossary และ deterministic Thai templates ที่มี version
- `app/extensions/ui/musician_summary_view.py` — word-wrapped explanation + evidence details
- `tests/extensions/test_musician_summary.py` — golden copy, invariants, validity และ identity tests

เลือก composition/wrapper ของ SummaryPanel เพื่อรักษาตาราง/กราฟ/handlers เดิม แล้วเสนอจุด mount เล็กที่สุดใน extension workbench ให้ผู้ใช้อนุมัติก่อนหากต้อง reparent/เปลี่ยนสถาปัตยกรรม layout ห้าม monkeypatch globals หรือเปลี่ยน EQ scoring เพื่อให้ prose ดูสอดคล้อง

Skill ใช้ในขั้นออกแบบ/ทบทวนภาษา ไม่ได้หมายความว่าแอปต้องเรียก Codex skill หรือ LLM ทุกครั้งที่เปลี่ยน A/B รุ่นแรกควรทำงาน local/offline ด้วย rules/templates: ผลเดิมให้ข้อความเดิม ไม่เสียเวลารอเครือข่ายและไม่ส่ง IR ออกนอกเครื่อง

## 5. Contract สำหรับคำอธิบาย

Input snapshot ต้องมี:

- A/B source signatures, analysis/config versions, active generation
- sample-rate/channel policy, onset/alignment mode, analysis windows, band definitions และ normalization/reference
- optional tone records, optional validated features พร้อม units/reasons
- optional verified pair/blend result พร้อม ratio/polarity/delay และ validity band
- locale, rules/glossary version, optional user listening priority เช่น “เก็บตัวไว”

แต่ละ `Claim` ต้องมี `claim_id`, `subject` (A/B/pair), `category`, `evidence_ids`, `interpretation_level`, `validity_reason`, `template_key` และ typed template parameters พร้อมหน่วย หาก claim ไม่มีหลักฐานหรือ source identity ไม่ตรง ต้องไม่แสดง

Output มี headline, descriptions ของ A/B, listening_focus ไม่เกิน 3 ข้อ, optional blend note, limitations และ evidence details

Optional fields ขาดได้: ขาด phase ไม่ควรทำให้สรุป tonal balance ที่ valid หาย แต่ต้องไม่พูดถึง blend เอง ระบุ per-category availability ไม่บีบทั้งคู่เป็น confidence score เดียว

## 6. กฎการสร้างข้อความที่ห้ามละเมิด

1. **Relative ก่อน absolute:** default เทียบ A กับ B การบอกว่า “ทั้งคู่โทนอุ่น” ต้องมี reference/calibration ที่ระบุ ไม่อนุมานจากการเทียบกันเอง
2. **ตัวเลขใหญ่กว่าไม่ใช่ดีกว่า:** อธิบาย character ไม่เลือกผู้ชนะ ถ้ารู้ goal ให้บอก “ลองเริ่มฟัง A หากต้องการ...” ไม่เปลี่ยน ranking เดิม
3. **ไม่สร้าง confidence ปลอม:** แสดง “ข้อมูลเพียงพอ / จำกัด / ยังสรุปไม่ได้” ตาม checks; ไม่ใช้ correlation หรือ valid coverage เป็น “มั่นใจ 98%”
4. **ไม่เติมช่องว่างด้วยคำสวย:** invalid, NaN, source mismatch, stale generation หรือ bug-affected producer ต้องออกเป็น limitation ไม่มี inference ว่า IR แย่
5. **ไม่ใช้ raw delta ต่างหน่วยจัดอันดับ:** แต่ละ category มี calibrated reporting threshold/scale แยกกัน; ใช้ user priority แล้วตามด้วย normalized effect ไม่ sort ms/dB/Hz รวมกัน
6. **Threshold ไม่ใช่ universal hearing limit:** เก็บใน versioned config, ระบุว่า provisional จนทดสอบ synthetic fixtures + listening review; ไม่ตั้ง cutoff ให้ “อุ่น/คม/กระชับ” จากความรู้สึกของ coder
7. **เหมือนกันก็พูดว่าใกล้กันได้:** ไม่บังคับทุก pair ต้องมี 3 differences และไม่ต้องอธิบาย A/B คนละ character หาก evidence เท่ากัน
8. **ตรวจ waveform context:** file leading silence/backtrack ไม่ใช่ pick attack; short/truncated/processed/minimum-phase IR ต้องมีข้อจำกัดประกอบตามข้อมูลที่ทราบ ห้ามเดา acquisition history จากชื่อไฟล์
9. **Blend ผูกกับ state จริง:** ratio, alignment, delay, polarity หรือ channel เปลี่ยน ต้อง invalidate claim; raw/onset/suggested ต้องระบุความหมาย
10. **คำศัพท์สม่ำเสมอ:** ใช้ “ย่านต่ำเก็บตัวเร็ว” สำหรับ decay, “มีน้ำหนักย่านต่ำ” สำหรับ magnitude และ “หัวโน้ตเด่น” เฉพาะ interpretation ที่มี evidence หลายตัว อย่าแทนคำเหล่านี้กัน
11. **Units ไม่หลอกตา:** coverage fraction ×100 ถ้าแสดง %, crest ratio แปลง `20log10` ถ้าจะแสดง dB; เก็บ canonical values เดิม
12. **ไม่มีการฟังจริงก็ไม่อ้างว่าฟังแล้ว:** listening advice เป็นขั้นตอนให้ผู้ใช้ตรวจด้วย DI/level-match ไม่ใช่ผลทดลองทางเสียงที่เกิดขึ้นแล้ว

## 7. Layout และ microcopy

- วางสรุปก่อน metric table; ใช้หัวเรื่อง “โทน”, “หัวโน้ตและหางเสียง”, “จุดต่างที่ควรฟัง”, “การผสม” เท่าที่มีข้อมูล
- ใช้ fixed A/B colors เดิม, ชื่อไฟล์แบบ middle-elide/full-path tooltip และอ่าน A/B ได้แม้ไม่เห็นสี
- Word wrap ภาษาไทย, ความสูงขยายตามข้อความ, body font ไม่น้อยกว่าของ UI ปัจจุบัน; ไม่ใช้ text box สูงคงที่ที่ตัดบรรทัด
- ที่ width แคบ stack A แล้ว B; ไม่บังคับเพิ่ม minimum width ของ workbench เดิม
- ปุ่ม: “ดูค่าที่รองรับ”, “ดูกราฟย่านนี้”, “คัดลอกสรุป”; details ต้องเข้าถึงด้วย keyboard ไม่พึ่ง hover อย่างเดียว
- เปลี่ยนคู่: “กำลังสรุป IR คู่ใหม่…” พร้อมซ่อนหรือ mark ข้อความเก่าว่าเป็นคู่ก่อนหน้า ห้าม export/copy เป็นคู่ใหม่
- Empty: “เลือก IR สองตัวเป็น A และ B เพื่อดูสรุปโทนและการตอบสนอง”
- Partial: “สรุปได้เฉพาะโทน — ข้อมูลหางเสียงของ B ยังไม่เพียงพอ”
- Failure: “ยังสรุปคู่นี้ไม่ได้: อ่าน IR B ไม่สำเร็จ ลองเลือกไฟล์ใหม่หรือสแกนอีกครั้ง”

## 8. Dependencies จาก Final Review

อ้างอิง [FINAL_REVIEW_2026-08-31.md](E:/Projects/BestIR/docs/FINAL_REVIEW_2026-08-31.md)

- B06/B07: identity/stale/invalid checks ต้องผ่านก่อน summary ใด ๆ อ้างว่าตรงกับคู่ปัจจุบัน
- B01–B04, B10–B11: อย่าสร้าง blend/phase interpretation จาก producer ที่ยังมีปัญหา
- B12/B13: units และ validity accessor ต้องถูกต้องก่อนนำค่ามาเป็น evidence
- B14 และ config-hash finding: cache result ต้องตรง source/config; cache hit ไม่ใช่เครื่องหมายรับรองความน่าเชื่อถือ
- B17: ใช้ result bundle จาก worker ไม่เรียก heavy DSP/fingerprint บน GUI เพียงเพื่อเขียน summary

ระหว่างแก้บั๊ก สามารถพัฒนา glossary/rules/view บน independent validated fixtures ได้ แต่ **ห้ามปิดบัง known bugs ด้วย prose ที่ฟังน่าเชื่อถือ** ใน runtime ให้ suppress affected categories จนผ่าน gates

## 9. Acceptance tests สำหรับส่งมอบ

1. Identical inputs → “ใกล้เคียงกัน” ไม่มี forced winner หรือ fabricated differences
2. Same magnitude but different validated time response → “โทนใกล้กัน” พร้อมอธิบายเฉพาะ temporal difference
3. Low magnitude สูงแต่ decay สั้น → “มีน้ำหนักย่านต่ำมากกว่า แต่เก็บตัวเร็วกว่า” ได้โดยไม่ขัดกัน
4. Broad low-mid boost ไม่มี sustained ridge → ไม่ใช้คำ boxy/อู้เป็นข้อสรุป
5. Short/truncated/noisy B → ไม่อธิบายว่า B กระชับกว่าเพราะอ่าน D20 ไม่ได้
6. Raw delay-only difference → ไม่เรียกว่า tone ต่าง, compression ต่าง หรือเล่นติดมือกว่า
7. Same features with gain-only change ภายใต้ gain-normalized mode → character claims ไม่เปลี่ยนเพราะความดัง
8. Swap A/B → subjects/comparatives/evidence พลิกถูกต้อง แต่ไม่มี direction bias
9. Rapid pair change/out-of-order callback → prose ทุกประโยคตรง active generation; stale ถูก suppress
10. Blend ratio/alignment/channel change → claim เดิมไม่ค้าง และข้อความต้องตรง verified processed sum ใหม่
11. NaN/inf/unknown fields/unit mismatch/config mismatch → ไม่มี crash หรือ fabricated estimate
12. All-invalid pair → ข้อจำกัดและ next action; ห้ามข้อความ “ไม่มีความต่าง” ที่แปลผิดว่าเหมือนกัน
13. Every claim resolves to evidence and reason; thresholds/rules version อยู่ใน report; repeat input ให้ข้อความเดิม
14. Thai/English long filenames + 1000×700 workbench + high-DPI → ไม่ตัดเนื้อความ ไม่มี horizontal scrolling เพื่ออ่านสรุป
15. Existing signatures, records, EQ score/ranking, source checksums และ legacy tests ไม่เปลี่ยน

## 10. ข้อความส่งต่อ AI coder แบบย่อ

> เพิ่ม “สรุปสำหรับนักดนตรี” ใน BestIR A/B Summary ตาม MUSICIAN_SUMMARY_SPEC_TH.md ใช้หลัก design:ux-copy ให้ภาษาไทยอ่านเป็นธรรมชาติ แยกโทนจาก temporal response และ trace ทุก claim ไปยัง evidence สร้าง pure rules/templates และ read-only adapter แยกโมดูล ไม่แก้ legacy EQ/DSP/global state ไม่ใช้ LLM/network เป็น dependency ของ summary และไม่อ้างว่าแอปฟังเสียงแล้ว ตรวจ bug dependencies จาก Final Review ก่อนเชื่อม real outputs เสนอจุด mount ของ UI และขออนุมัติหากเป็น architectural change เก็บ technical details เดิมไว้ และส่ง tests สำหรับเหมือนกัน/ต่างด้านเวลา/invalid/stale/swap/blend-state/ภาษาไทยครบ
