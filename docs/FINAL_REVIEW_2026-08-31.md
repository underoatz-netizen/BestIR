# BestIR — Final review: DSP correctness, bugs and usability

วันที่ตรวจ: 2026-08-31 · commit: `db6e9f2f78cd850b6cec157aa7276a939e43a86c`

> อัปเดตสถานะล่าสุด: ดูหัวข้อ **"Wave 6 QA addendum (2026-09-02)"** ด้านล่าง — เนื้อหาใต้บรรทัดนี้อ้างอิงสถานะ ณ commit `db6e9f2` เท่านั้น

## ผลสรุป

**ยังไม่ผ่าน final QA สำหรับส่วน Compare / Response Search / Blend Export** แม้ชุดทดสอบปัจจุบันผ่าน 93/93 รายการ เพราะพบข้อผิดพลาดที่ทำซ้ำได้ทั้งในตัวเลข DSP และการเชื่อมต่อ UI โดยเฉพาะผล preview ไม่ตรงกับ processing ที่ใช้ export, sample rate ผิด, stale A/B และคำเตือน cancellation ผิดความหมาย

การตรวจนี้ไม่ได้แก้ production code, legacy EQ/ranking, source IR หรือไฟล์ EXE มีเพียงเอกสารและ diagnostic script ใหม่ การใช้ code-review และ design-critique ทำให้แยกตรวจ numerical oracle, ปุ่มจริง, async callback และ layout แทนการใช้ unit-test pass เป็นข้อสรุปเพียงอย่างเดียว

## วิธีตรวจและข้อจำกัด

- `python -m pytest tests -q --basetemp=E:\Projects\BestIR\.test-tmp\review-20260831 -p no:cacheprovider` → **93 passed in 25.87s**
- `python -m app.main --selftest` → OK
- `python -m app.extended_main --selftest` → OK; entry point นี้ใช้ selftest เดียวกับ legacy จึงไม่ใช่ independent DSP-extension validation
- สร้าง IR สังเคราะห์และ cache/settings แยก ไม่ใช้หรือแก้ library IR จริง
- ทดสอบ export ด้วย `QPushButton.click()` และจับการเปิด directory dialog; ทดสอบ DSP ด้วยคำตอบที่กำหนดได้ ไม่ใช้ผล prediction เป็น oracle ของตัวเอง
- รัน background pair worker จริงสำเร็จหนึ่งคู่ และตรวจ thread ที่ทำ fingerprint ใน callback
- Render widgets จริงด้วย Qt offscreen/Fusion พร้อม Windows Segoe UI/Consolas ที่โหลดให้โหมดทดสอบ ตรวจ 6 tabs, ขนาด 1280×880 และ 1000×700; หน้าหลัก 1500×900 และ 1280×720; ชื่อไฟล์ยาว
- รอบแรก offscreen ไม่มีฟอนต์เลย จึง **ไม่นับ** ภาพตัวอักษรสี่เหลี่ยม/geometry ของรอบนั้นเป็นบั๊ก production
- ยังไม่ได้ทดสอบ native desktop interaction, audio-device playback/re-amping, DPI 125–200%, packaged EXE รอบนี้ หรือ OpenGL 3D บน GPU จริง ไม่มีการอ้างว่าขอบเขตเหล่านี้ผ่าน

เครื่องมือทำซ้ำ: [final_review_probe.py](E:/Projects/BestIR/docs/review_tools/final_review_probe.py)

```powershell
python docs/review_tools/final_review_probe.py
```

Script เป็น diagnostic collector ไม่ใช่ test suite ที่ assert ว่าระบบถูกต้อง จะสร้าง directory ใหม่ใต้ `.test-tmp` แล้วพิมพ์ observations รวมถึงค่าที่ผิดออกมา

หลักฐานรอบสุดท้าย: [results.json](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/results.json) ภาพและผลลัพธ์ใต้ `.test-tmp` เป็น local ignored artifacts; หากส่งงานออกนอก workspace ให้แนบ directory นี้หรือรัน script ใหม่

## Release blockers ที่ยืนยันแล้ว

### B01 · P1 — Blend preview ไม่ใช่สัดส่วนเดียวกับ export

ตำแหน่ง: [pair_compare.py:99](E:/Projects/BestIR/app/extensions/pair_compare.py:99), [processing.py:84](E:/Projects/BestIR/app/extensions/processing.py:84), [pair_compare.py:261](E:/Projects/BestIR/app/extensions/pair_compare.py:261)

- Preview ใช้ `A + r*B` แต่ processing ใช้ `(1-r)*A + r*B` ขณะที่ UI ระบุ 0–100% B
- Synthetic A impulse = 0.8, B = 0.2: ที่ 100% B preview ≈ 0 dB แต่ processing ≈ −13.9794 dB ความคลาดเคลื่อน RMS = **13.9794 dB**
- `verified_rms_db` กลับรายงาน **0.0** เพราะ `_verify_against_time_domain` ทำ FFT และสูตรเดียวกับ prediction ซ้ำ ไม่ได้สร้าง time-domain aligned sum อิสระ
- แก้ใน extension โดยกำหนด gain convention หนึ่งเดียวให้ preview/risk/audio/export และทำ oracle จาก actual processed samples
- Gate: 0% = A, 100% = B, 50% = half-amplitude sum; เทียบ complex response/FFT ของ export buffer ทุกสัดส่วน พร้อม gain/normalization ที่ระบุชัด

### B02 · P1 — ต่าง sample rate แล้วความถี่ใน blend ผิด

ตำแหน่ง: [processing.py:68](E:/Projects/BestIR/app/extensions/processing.py:68), [pair_compare.py:28](E:/Projects/BestIR/app/extensions/pair_compare.py:28)

- ทั้ง analysis และ blend ใช้ sample rate ของ A กับ samples ของ B โดยไม่มี resampling หรือ reject
- A=48 kHz, B=96 kHz ที่บันทึก sine 1 kHz; buffer ที่ใช้ export เมื่อเลือก 100% B มี peak **500.244 Hz** และไม่มี warning
- ให้เพิ่ม pair-preparation adapter ที่เลือก common analysis/output rate, resample อย่างมี provenance และแปลงหน่วย delay ให้ถูกต้อง ก่อนส่งเข้า algorithms ที่ต้องการ same-rate input
- ระหว่างที่ยังไม่รองรับ ต้องปฏิเสธต่าง rate พร้อมเหตุผล ห้ามเปลี่ยนเฉพาะ metadata
- Gate: 44.1/48/96 kHz, ทั้ง A→B และ B→A, frequency/duration/delay คงค่าทางกายภาพ

### B03 · P1 — Alignment ใช้ time origin คนละแบบกับ processing

ตำแหน่ง: [pair_compare.py:65](E:/Projects/BestIR/app/extensions/pair_compare.py:65), [pair_compare.py:158](E:/Projects/BestIR/app/extensions/pair_compare.py:158), [processing.py:40](E:/Projects/BestIR/app/extensions/processing.py:40)

- `_mono()` ตัด onset ของแต่ละไฟล์ก่อนประมาณ delay แต่ `apply_alignment()` ใช้ full prepared buffer
- B ที่ช้ากว่า A จริง 120 samples: pair รายงาน 0 samples; processed B ยังช้า **120 samples** เช่นเดิม
- `raw` กับ `onset` preview ในกรณีนี้เหมือนกันทุก bin แม้ timing ตามไฟล์ต่างกัน
- นอกจากนี้ positive delay หมายถึง B มาช้า แต่ preview ใช้ negative FFT phase ramp ซึ่ง delay B เพิ่ม ขณะที่ processing ใช้ positive ramp เพื่อ advance B — เป็น sign inconsistency ที่เห็นใน source
- ต้องนิยาม native/onset/residual/total-applied delay แยกกัน และใช้ policy เดียวตั้งแต่ analysis ถึง export
- Gate: known ±integer/fractional delay, polarity inversion, leading silence, swapped A/B และ source with different onset offsets; ห้ามทดสอบเฉพาะ onset-cropped arrays

### B04 · P1 — Severe cancellation แสดงเป็น “Safe”

ตำแหน่ง: [phase_blend_view.py:216](E:/Projects/BestIR/app/extensions/ui/phase_blend_view.py:216)

- DSP คืน cancellation เป็น **positive loss** แต่ UI ตรวจ `< -6` / `< -3`; ค่าบวกจึงเข้า Safe เสมอ
- Perfect-cancellation synthetic probe ให้ loss ≈ 601 dB จาก numerical floor ของ algorithm และ UI แสดง `✓ Comb Risk: Safe` ตัวเลขนี้เป็นผล test cancellation สมบูรณ์ ไม่ใช่ acoustic measurement ที่อ้างความแม่นยำ 601 dB
- เปลี่ยน sign/threshold ให้สอดคล้อง contract; ไม่มี valid bins ให้ Unknown ไม่ใช่ Safe
- Risk/notch/sensitivity ต้องคำนวณตาม ratio และ alignment ปัจจุบัน หรือระบุชัดว่าเป็น reference 50/50 แยกจาก current preview
- Gate: known safe/moderate/deep-cancellation และ unknown; ค่า risk เปลี่ยนสัมพันธ์กับ control state

### B05 · P1 — ปุ่ม export ทั้งสามไม่ได้ต่อกับ workbench handlers

ตำแหน่ง: [compare_workbench.py:77](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:77), [phase_blend_view.py:130](E:/Projects/BestIR/app/extensions/ui/phase_blend_view.py:130)

- ปุ่ม emit `export_aligned_b`, `export_blend`, `export_report` แต่ไม่มี connection จาก signals เหล่านี้ไป `_export_*` ของ workbench
- ทดสอบกดจริง 3 ปุ่ม หลัง pair พร้อม: directory dialog เปิด **0 ครั้ง**
- Test ปัจจุบันเรียก `_export_aligned_b()` / `_export_blend()` / `_export_report()` โดยตรง จึงไม่จับปัญหานี้
- ต่อ signals ใน adapter และ disable export ตั้งแต่เริ่มต้น/ขณะรอ/เมื่อ invalid หรือ stale จัดการ I/O failure ใน UI
- **อย่าแก้แค่ต่อปุ่มแล้วปล่อยใช้งาน** ต้องผ่าน B01–B04/B06 ก่อน เพราะ handlers เดิมยังใช้ผล DSP ที่ผิดได้
- Gate: click → dialog → new output → reopen/verify → source checksum unchanged; cancel/read-only directory/error flows ต้องผ่าน

### B06 · P1 — เปลี่ยนคู่ A/B แล้วรับผลของคู่เก่าได้

ตำแหน่ง: [compare_workbench.py:173](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:173), [compare_workbench.py:196](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:196)

- `_invalidate()` ไม่ invalidate request ID ทันที รอ `_compute_pair()` อีก 250 ms จึงเปลี่ยน ID; `_last_pair`, `_last_blend`, stored matrices และ worker identities ยังเก่า
- Repro: A/a + B/b กำลังประมวลผล → เปลี่ยน B/c → ส่งผล request เดิมระหว่าง debounce; header แสดง **c.wav** แต่ `_last_pair.key_b` เป็น **b.wav** และ status แสดง completed pair
- Fingerprints/phase ใน callback อ่าน `self.rec_a/b` ปัจจุบัน ทำให้ข้อมูลหลายแท็บอาจมาจากคนละคู่ ผลเก่ายังใช้กับ export ปัจจุบันได้หากต่อปุ่มแล้ว
- เพิ่ม immutable generation context `(A signature, B signature, config hash, generation)` เปลี่ยนทันทีเมื่อ selection เปลี่ยน ใช้ guard เดียวกันกับ success/failure ของทุก worker
- ล้างหรือแสดง old result ว่า stale อย่างชัดเจน และห้าม export จน active pair พร้อม
- Gate: rapid A/B/swap/tab switching, delayed success และ delayed failure; ทุกกราฟและ export report ต้องมี identity ตรง header

### B07 · P1 — Invalid B อาจรายงาน OK และ renderer โยน exception

ตำแหน่ง: [pair_compare.py:21](E:/Projects/BestIR/app/extensions/pair_compare.py:21), [pair_compare.py:60](E:/Projects/BestIR/app/extensions/pair_compare.py:60), [spectrogram_view.py:119](E:/Projects/BestIR/app/extensions/ui/spectrogram_view.py:119)

- A valid + B silent → pair และ blend **status='ok'** เพราะ error branch เลือก status ของ A เมื่อไม่ใช่ TOO_SHORT
- ส่ง silent SpectrogramResult เข้าหน้าแสดงผล → `ValueError: not enough values to unpack (expected 2, got 0)` เนื่องจาก magnitude ไม่มี matrix
- Propagate invalid side อย่างถูกต้อง; view ตรวจ status/shape/axes ก่อน render และแสดง no-data reason ไม่ให้ช่องว่างหรือป้าย Safe กลบ invalid state
- Gate: silent/nonfinite/unreadable/too-short ทั้ง A และ B, null matrices และ zero reliable spectrum

### B08 · P1 — Presets ไม่ได้ส่งเป้าหมายไป ranking

ตำแหน่ง: [response_search_panel.py:220](E:/Projects/BestIR/app/extensions/ui/response_search_panel.py:220), [response_search_panel.py:231](E:/Projects/BestIR/app/extensions/ui/response_search_panel.py:231), [advanced_matching.py:88](E:/Projects/BestIR/app/extensions/advanced_matching.py:88)

- `Tight Low` กำหนด `targets={'d20':25.0}` แต่ `_apply_preset()` ทิ้ง targets และ emitted request ไม่มี field นี้ ทั้งสอง search adapters ไม่ส่ง targets ให้ ranking
- Backend จึงใช้ library median แทนเป้าหมาย Tight Low ทำให้ชื่อ preset ไม่ได้สะท้อน objective ที่ผู้ใช้เลือก
- เก็บ/แสดง desired value + units แยกจาก weight แล้วส่ง immutable request ครบทุก entry point
- Gate: เปลี่ยน library median โดยคง desired target เดิมแล้วคำอธิบาย target ต้องไม่เปลี่ยน; synthetic candidates ต้อง rank ตาม target ไม่ใช่ค่ากลางของ library

### B09 · P1 — CSD ในหน้า Compare แสดงเพียงตัวที่เสร็จล่าสุด

ตำแหน่ง: [compare_workbench.py:304](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:304), [csd_fallback.py:23](E:/Projects/BestIR/app/extensions/ui/renderers/csd_fallback.py:23)

- A และ B ถูกส่งเข้า plot เดียว; renderer `clear()` ทุกครั้งและไม่ใช้ `mode` เพื่อเปรียบเทียบ
- Repro apply A แล้ว B → เหลือ **1 image** ซึ่งเท่ากับ B ทุกค่า ไม่มี A/B selector หรือ label ระบุตัวที่กำลังแสดง; completion order จึงเปลี่ยนกราฟที่ผู้ใช้เห็น
- ทำ explicit A/B/overlay หรือ side-by-side บน common axes พร้อม numeric evidence แยก A/B; เลือก active source อย่าง deterministic
- Gate: สลับ completion order แล้ว layout/data identity ไม่เปลี่ยนความหมาย

## ข้อผิดพลาดและข้อจำกัดอื่นที่ต้องเก็บงาน

| ID / ระดับ | หลักฐานและตำแหน่ง | แนวแก้ / acceptance |
|---|---|---|
| B10 / P2 | [pair_compare.py:257](E:/Projects/BestIR/app/extensions/pair_compare.py:257) ใส่ square root ซ้ำใน phase RMS; spectra กลับขั้ว 180° ได้ **101.554°** | แปลง radians RMS เป็น degrees เพียงครั้งเดียว; known phase offsets ต้องตรง oracle |
| B11 / P2 | [phase.py:40](E:/Projects/BestIR/app/extensions/phase.py:40) ใช้ `any(channel)` แล้วใช้ mask เดียวกับทุกช่อง; L impulse/R silent ทำให้ R มี phase/GD finite **192 bins** | validity per channel; unwrap/gradient แยก contiguous valid runs; เพิ่ม channel selector ไม่สรุป channel 0 เป็นทั้งไฟล์ |
| B12 / P2 | [summary_panel.py:23](E:/Projects/BestIR/app/extensions/ui/summary_panel.py:23), [metric_card.py:86](E:/Projects/BestIR/app/extensions/ui/widgets/metric_card.py:86): coverage fraction 0.250978 แสดง **0.251%** แทน 25.10%; crest peak/RMS ถูกอธิบายเป็น dB | ใช้ unit formatter: fraction×100 สำหรับ %, crest `20log10(ratio)` ถ้าจะแสดง dB; อย่าเปลี่ยน cached raw values |
| B13 / P2 | [csd_view.py:105](E:/Projects/BestIR/app/extensions/ui/csd_view.py:105) อ่าน `D20_<band>_valid` แต่ producer ใช้ `D20_<band>_ms_valid`; injected valid 100 ms ยังแสดง invalid/noisy | ใช้ contract accessor เดียว; distinguish invalid/noisy/unsupported/insufficient duration |
| B14 / P2 | [cache.py:39](E:/Projects/BestIR/app/extensions/cache.py:39): SQLite connection สร้างบน GUI thread; worker read คืน None แม้ main read hit; worker insert ไม่บันทึกและไม่แจ้ง error | worker-local connection หรือ single cache owner/queue พร้อม concurrency policy; ทดสอบข้าม thread จริง ไม่ใช่ sequential cache test |
| B15 / P2 | [spectrogram_view.py:131](E:/Projects/BestIR/app/extensions/ui/spectrogram_view.py:131): A 78 frames/B 4 frames → Difference **0 images**; footer ไม่อธิบาย incompatibility; A/B autoscale เวลาคนละช่วง | shared analysis grid หรือ compare เฉพาะ valid overlap พร้อม masks; shared time/frequency axes; explicit no-overlap reason, dB colorbar, diverging diff scale centered at 0 |
| B16 / P2 | [compare_workbench.py:397](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:397) fingerprint แค่ first 400 ก่อน shortlist ต่างจาก toolbar ที่ tone-shortlist top 40; ไม่ forward max_tone_db โดยตรงทำให้ cutoff default 6 dB ยังคุม | รวม request pipeline ใน extension controller เดียว; candidates/tone anchor/constraints ต้องเหมือนกันจากทุก entry point |
| B17 / P2 | [compare_workbench.py:205](E:/Projects/BestIR/app/extensions/ui/compare_workbench.py:205) callback ทำ fingerprint/phase บน GUI thread; genuine worker probe พบ fingerprint **175.9 + 14.3 ms** บน GUI | ย้าย preparation/fingerprint/phase เข้า result bundle ของ worker; GUI render เท่านั้น; ทดสอบ event-loop latency ใน cold-cache path |
| B18 / P2 | [main_window_adapter.py:72](E:/Projects/BestIR/app/extensions/ui/main_window_adapter.py:72), [main_window_adapter.py:163](E:/Projects/BestIR/app/extensions/ui/main_window_adapter.py:163) เขียน global pens และ `_TOP5_BG` ใน legacy modules | ไม่สอดคล้อง No State Corruption แม้ไม่ได้แก้ source legacy; ใช้ instance-local styling/proxy/delegate และตรวจอีก legacy window ใน process เดียว |

### จุดที่ตรวจจาก source แล้วควรทดสอบก่อน sign-off เพิ่มเติม

- **OpenGL 3D**: [csd_opengl.py:39](E:/Projects/BestIR/app/extensions/ui/renderers/csd_opengl.py:39) ส่ง tuple `(vertices, faces)` เข้า argument `vertexes` แล้วนำ GLMeshItem เข้า 2D PlotWidget; CsdView ไม่มี runtime exception fallback เส้นทางนี้ไม่ได้รันในเครื่องที่ไม่มี OpenGL จึงยัง sign-off ไม่ได้ ให้ใช้ GLViewWidget/mesh API ให้ตรงและทดสอบ context/render failure
- **Cache identity**: [fingerprint.py:19](E:/Projects/BestIR/app/extensions/fingerprint.py:19) ใช้ constant `CFG_HASH` แทน effective prep/env/tf/phase/decay configuration; different settings อาจได้ cached result เดิม
- **Long-file cap**: [preprocessing.py:99](E:/Projects/BestIR/app/extensions/preprocessing.py:99) ใช้ `max(onset+cap, tail_end+rms_win)` ทำให้ sustained tail ที่ยาวกว่า cap ยังผ่านมาทั้งก้อน ต้องตรวจ long IR ไม่ให้ UI/worker ใช้ memory เกินงบ
- **Stereo analysis policy**: CSD/pair/spectrogram ใช้ signed mean ของ channels ในบางทาง; anti-phase stereo อาจหักล้างเป็นศูนย์ ต้องมี explicit per-channel / power aggregation / mono-fold policy ที่สอดคล้อง analysis type
- **Worker lifecycle**: repeated search, rapid pair replacement และ closing window ยังไม่มี centralized cancellation/retention/shutdown policy ครบ ไม่พบ native crash ใน probe หนึ่งคู่ แต่ไม่เท่ากับผ่าน stress/lifecycle test
- **Export edge cases**: clipping/headroom/fractional-delay overshoot, source/destination collision, simultaneous same-name export, disk-full/permission failure, reopen-verify และ complete processing provenance ต้องทดสอบเพิ่มเติมก่อนเรียกว่า non-destructive export ผ่านครบ

## Layout / UX ที่ควรปรับ โดยคง EQ workflow เดิม

ภาพอ้างอิงจาก widgets จริง: [หน้าหลัก](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/main_small.png), [Summary 1000×700](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/small_summary.png), [Phase/Blend](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/small_phase.png), [Spectrogram](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/spectrogram.png), [ชื่อไฟล์ยาว](E:/Projects/BestIR/.test-tmp/review-20260831-fdq1ahzg/long_filenames.png)

สิ่งที่ควรรักษา: fixed A/B identity colors, A/B deck มองเห็นทุกแท็บ, Summary เป็น entry point, แยก Compare จาก EQ เดิม โครงสร้างนี้รองรับงานวิเคราะห์ได้ดี ไม่จำเป็นต้อง redesign ทั้งแอป

| Priority | ปัญหาที่พบ | ข้อเสนอแบบ additive |
|---|---|---|
| U01 / สูง | หน้าหลัก resize 1280×720 แล้ว Qt ขยายเป็น **1551×720**; library min 560 + inspector min 320 + center action-row min ≈663 | ใช้ responsive layout adapter เฉพาะ ExtendedMainWindow: inspector collapse/drawer และ action row wrap/overflow; ห้ามลดทุกอย่างด้วย font เล็กลง |
| U02 / สูง | Search ใน library กว้าง **33 px** จนแทบพิมพ์ไม่ได้; filters ทั้งหมดอัดแถวเดียว | ให้ Search เต็มแถวและ min usable width; ย้าย SR/Ch/Tag/Flatness ลง filter row ที่พับได้; คง filter signals และ logic เดิม |
| U03 / สูง | A/B spectrogram เวลาคนละสเกล ทำให้ persistence ดูคล้ายทั้งที่ต่างกันมาก; diff blank | Link axes/cursor, shared dB reference ที่เลือกได้, colorbars และ explicit data validity; เลือก A/B/Diff บนจอแคบแทนบังคับ 3 plots แคบตลอด |
| U04 / กลาง | ชื่อ IR ยาวถูกตัดตรงท้ายที่ต่างกัน A/B เหลือ prefix เหมือนกัน; inspector metadata ถูกตัด | Middle-elide ชื่อโดยรักษาส่วนท้ายที่ระบุ mic/position พร้อม full-path tooltip/copy; metadata แบ่ง 2–3 บรรทัด ไม่เปลี่ยน underlying path |
| U05 / กลาง | Waveform แสดง Hilbert envelope เท่านั้น, default 0–500 ms ทำให้ attack บีบที่ซ้ายและ A/B peak labels ทับกัน | Toggle signed waveform / Hilbert / RMS, zoom presets Attack 0–10 ms / Tail / Full, linked crosshair และแยกตำแหน่ง marker labels |
| U06 / กลาง | Phase plots ไม่มี visible A/B legend, แกน/ตัวเลขบางส่วนเล็ก; ไม่มี raw/onset/suggested control ในหน้าใช้จริง | เพิ่ม legends, alignment selector ที่ระบุ applied delay, manual polarity/delay preview แยกจาก source; numeric ratio input หรือ discrete slider ให้ตรง 5 ratio bins |
| U07 / กลาง | Search แสดง weight มาก่อน desired outcome; preset button+combo ซ้ำ; candidate click เปิดได้แค่ explanation | Simple mode: desired response + tone tolerance; Advanced: weights/policy; แสดง tone anchor/source ของ shortlist, ปุ่ม Set A/Set B/Audition/Compare บน candidate; unify กับ toolbar search |
| U08 / กลาง | Summary มี n/a โดยไม่เห็นเหตุผลทันที; เลือก “ความต่างสำคัญ” โดย sort raw absolute values ต่างหน่วยกัน | ระบุ Unknown/too short/low confidence; จัดลำดับผ่าน dimensionless normalized effect หรือ user priority และอย่าเรียกค่าที่สูงกว่าว่าเสียงดีกว่าอัตโนมัติ |
| U09 / กลาง | Theme ใส่ background/border ให้ labels หลายระดับจนเป็นกล่องซ้อน; focus/checkbox state ต้องตรวจ keyboard จริง | ใช้ object-scoped component styles; labels โปร่งใสใน card; focus ring และ checked/unchecked แยกชัด; ตรวจ keyboard Tab/Space/Enter และ high-DPI ก่อน sign-off |

U01/U02 เป็นข้อจำกัดที่พบในหน้าจอปัจจุบันซึ่งสืบทอด layout เดิม ไม่ได้สรุปว่าทั้งหมดเป็น regression ที่เพิ่งเกิดจาก extension

Suggested usable flow: **EQ shortlist เดิม → เลือก A/B → Summary → เจาะ Waveform/CSD/Spectrogram/Phase → Audition → Export copy**. ต้องทำให้ผล Search ส่งเข้า flow นี้ได้โดยไม่ให้ผู้ใช้หาไฟล์เดิมใน library ด้วยตัวเองอีก

## ลำดับส่งต่อให้ AI coder

1. **Red tests ก่อน**: เปลี่ยน observations B01–B09 เป็น regression tests ที่ fail กับ commit นี้ ใช้ independent DSP oracle และจริง UI click/event-loop ไม่เรียก export handlers ข้าม UI
2. **Pair DSP contract**: B01–B03/B07/B10–B11; เพิ่ม common-rate/time-origin/channel-policy adapter โดยไม่แก้ legacy analysis records หรือ EQ scoring
3. **Controller safety**: B05–B06/B14/B17; immutable request generation, guarded rendering/export, worker-owned cache access, error state
4. **Meaningful comparison/search**: B04/B08–B09/B12–B13/B15–B16; numerical meaning ต้องถูกก่อนปรับกราฟให้สวย
5. **Responsive extension UI**: U01–U09 และเลิก global mutation B18; architectural reparent/replacement ของ layout ให้เสนอจุดเชื่อมและขออนุมัติก่อนตาม Zero-Breakage Policy
6. **Release gate**: legacy regression + new red-tests turned green + source checksums + native desktop/high-DPI + GL available/unavailable/runtime failure + real export reopen + packaged EXE smoke; แก้ QA document ให้สะท้อนขอบเขตที่ทดสอบจริง

อย่า refactor legacy DSP, เปลี่ยน existing score/selection semantics หรือรีบต่อ export ให้ทำงานก่อน pair correctness ผ่าน ใช้ extension modules, adapters และ opt-in UI integration ตามขอบเขตเดิม

## Requirement เพิ่มเติม: Summary เป็นภาษานักดนตรี

ผู้ใช้ขอให้ Summary ใน A/B อธิบายโทนและการตอบสนองด้วยภาษาที่นักดนตรีเข้าใจ ไม่ใช่แสดงแต่ตัวเลขหรือแปลศัพท์ตรงตัว เพิ่มข้อกำหนดและตัวอย่างไว้ใน [MUSICIAN_SUMMARY_SPEC_TH.md](E:/Projects/BestIR/docs/MUSICIAN_SUMMARY_SPEC_TH.md) โดยใช้ skill `design:ux-copy` วางภาษาและ hierarchy

เอกสารครอบคลุม tone/response/pair distinction, evidence-based Thai glossary, optional read-only input adapter, pure description rules, UI states และ acceptance tests นี่เป็นสเปกส่งต่อ ยังไม่ได้แก้ production UI; ต้องผ่าน validity/identity/DSP gates ที่เกี่ยวข้องก่อนใช้คำอธิบายกับผลวิเคราะห์จริง

## Wave 6 QA addendum (2026-09-02)

สถานะ ณ commit `e6f049b` (Wave 5 UI pass) เป็นส่วนเพิ่มบนบันทึกนี้; เนื้อหาข้างบนคงเป็นหลักฐาน ณ `db6e9f2` ตามเดิม

- **ความคืบหน้า**: Wave 1-5 แก้ B01-B18 และ U01, U03-U09 แล้ว; `python -m pytest tests -q` ผ่าน **210 tests** (จากเดิม 93) และ `python docs/review_tools/final_review_probe.py` รันผ่าน โดยยืนยันว่า fingerprint ทำงานนอก GUI thread (`on_gui_thread: false`)
- **ยังไม่ทดสอบ (NOT RUN)**: native Windows desktop interaction และ DPI 125-200%, audio-device playback/re-amping, packaged EXE smoke รอบนี้, และ OpenGL 3D บน GPU จริง ห้ามอ้างว่าขอบเขตเหล่านี้ผ่าน; release gate ข้อ 6 (native desktop/high-DPI, GL, EXE reopen) จึงยังไม่ครบและ QA ยังไม่ sign-off
- **เลื่อน (deferred)**: U02 (search 33 px / filter row) เลื่อนไป Wave 7 พร้อมงาน native DPI/interaction gate; U01-U09 จึงยังไม่ถือว่าปิดครบทั้งชุด
- **diagnostic probe**: `docs/review_tools/final_review_probe.py` เพิ่มการตรวจ B06 ว่า stale result ของ request เก่า (ID 42) ถูก reject และไม่กลายเป็น pair ที่ active/exportable (`stale_pair_rejected`) การเปลี่ยนนี้เป็นเครื่องมือวินิจฉัยเท่านั้น ไม่กระทบ production code
