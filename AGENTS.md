# BestIR — IR ตัวช่วยสำหรับงานนี้

Desktop app (Windows, Python 3.12+, PySide6/PyQt + pyqtgraph) สำหรับโหลดโฟลเดอร์ IR เพื่อวิเคราะห์โทน → จัดอันดับตาม target → ฟัง A/B → export ไฟล์ที่รอด

## คำสั่ง run/verify

```powershell
python -m pytest tests -q            # full suite (รวม extensions, 93+ tests)
python -m pytest tests/extensions -q -p no:cacheprovider
python -m app.main --selftest
python -m app.extended_main --selftest   # ใช้ selftest เดียวกับ legacy ไม่ใช่ independent validation
python docs/review_tools/final_review_probe.py  # diagnostic collector (ไม่ใช่ test suite)
```

- pytest.ini: `testpaths = tests`
- UI tests ใช้ Qt offscreen/Fusion + fonts ที่โหลดให้ (Windows Segoe UI/Consolas) อย่าลืม pattern นี้เมื่อเพิ่ม UI test
- `.test-tmp/` คือ artifacts ที่ ignore ได้ ใช้ `--basetemp` แยกเมื่อต้อง race

## โครงสร้าง

- `app/core/` — legacy: audio_io, analysis (DSP), matching, presets, cache, scanner, audition, exporter, tonematch
- `app/ui/` — legacy UI: model, library_panel, plot_panel, screen_panel, inspector_panel, main_window, workers
- `app/extensions/` — additive extension (Tier 0–2): contracts, adapters, cache, preprocessing, time_frequency, csd, decay, phase, envelope, fingerprint, pair_compare, processing(+_export), spectrogram, advanced_matching, profiles, service
- `app/extensions/ui/` — compare_workbench, summary_panel, waveform_view, csd_view, spectrogram_view, phase_blend_view, response_search_panel, main_window_adapter, workers, renderers/ (csd_base/fallback/opengl), widgets/ (ab_header, metric_card, validity_chip)
- `tests/synth.py`, `tests/extensions/fixtures.py` — สังเคราะห์ IR/สัญญาณสำหรับ test (ใช้เป็น oracle อิสระ ห้ามใช้ผล prediction ของตัวเอง)
- `dist/` — BestIR.exe / BestIRExtended.exe (build: `python -m PyInstaller BestIR.spec|BestIRExtended.spec --noconfirm`)
- Cache: `%LOCALAPPDATA%\BestIR\cache.json` + sidecar cache ใน `app/extensions/cache.py`

## กฎสำคัญ (Zero-Breakage Policy)

1. **ห้าม refactor legacy DSP** (`app/core`, `app/ui`) ห้ามเปลี่ยน existing score/selection semantics, source checksums, global state (`QApplication` pens, `_TOP5_BG` — วาง B18 ไว้เป็น global mutation ต้องเลิก)
2. แก้ด้วย extension modules / adapters / opt-in UI integration เท่านั้น
3. ห้าม monkeypatch globals, ห้ามแก้ EQ scoring ให้ prose ดูสอดคล้อง
4. ห้ามเรียก heavy DSP/fingerprint บน GUI thread — ทำใน worker result bundle
5. ห้ามต่อ export/summary ให้ทำงานจริงก่อน DSP correctness gates ผ่าน (B01–B04, B06, B07, B10–B11)
6. UI change ที่ reparent/เปลี่ยน architectural layout → เสนอจุดเชื่อมและขออนุมัติก่อน

## สถานะ release (docs/FINAL_REVIEW_2026-08-31.md, commit db6e9f2)

**ยังไม่ผ่าน final QA** สำหรับ Compare / Response Search / Blend Export — tests ผ่าน 93/93 แต่มี bug ที่ทำซ้ำได้:

- **P1**: B01 blend preview ≠ export convention (A+r·B vs (1−r)A+rB); B02 ต่าง sample rate มี resampling/alignment ผิด; B03 time-origin คนละแบบ (mono กัน onset-cut) + sign ของ delay ramp กลับซ้าย; B04 cancellation positive loss แสดงเป็น Safe (UI เช็ค `< -6`); B05 export signals ไม่ connect เข้า workbench handlers (กดปุ่มเปิด dialog 0 ครั้ง); B06 stale generation เมื่อเปลี่ยนคู่เร็ว ๆ (header แสดง B ใหม่ แต่ data เก่า); B07 invalid/silent B → status='ok' + renderer โยน exception; B08 presets ทิ้ง targets ไม่ส่งไป ranking; B09 CSD plot เดียวแสดงหน้าเสร็จล่าสุด
- **P2**: B10 phase RMS squareroot ซ้ำ, B11 channel validity, B12 unit formatter (0.251% แทน 25.10%), B13 `D20_<band>_ms_valid` mismatch, B14 SQLite thread-safety, B15 spectrogram A/B frame incompatible, B16 fingerprint pipeline ต่างจาก toolbar, B17 GUI-thread fingerprint (meas: 175.9+14.3 ms), B18 global mutation
- ยังไม่ sign-off: OpenGL 3D (renderer ใช้ GLMeshItem ใน 2D PlotWidget), cache identity (CFG_HASH constant), long-file cap, stereo analysis policy, worker lifecycle, export edge cases
- UX backlog: U01–U09 (responsive 1280×720, search 33 px, 3-plot spectrogram, middle-elide filenames, waveform zoom presets, phase legend/selector, search UI simplify, summary n/a reasons, theme focus)

## สเปก musicians summary (docs/MUSICIAN_SUMMARY_SPEC_TH.md)

เพิ่มส่วน "สรุปสำหรับนักดนตรี" ให้ Summary — ข้อความแยก **โทน (magnitude)** กับ **temporal response (decay/attack/GD)** เสมอ ห้ามสรุปจาก raw delta ต่างหน่วย และทุก claim ต้อง trace ไป evidence:

- เสนอสร้าง: `app/extensions/musician_summary/{contracts,adapter,rules,phrases_th}.py` + `app/extensions/ui/musician_summary_view.py` + `tests/extensions/test_musician_summary.py`
- pure rules/templates + read-only adapter, **no LLM/network dependency**
- หลังระหว่างแก้ bug: ใช้ fixtures ได้ แต่ runtime ให้ suppress categories ที่ยังไม่ผ่าน B-gates; ห้ามปิดบัง known bugs ด้วย prose
- acceptance: identical→"ใกล้เคียงกัน", swap ไม่มี direction bias, invalid→limitations, blend ถูก invalidate ตาม ratio/alignment/channel

## ลำดับส่งต่อ (จาก review)

1. Red tests จาก B01–B09 ก่อน (independent DSP oracle + จริง click/event-loop)
2. Pair DSP contract (B01–B03/B07/B10–B11) — common-rate/time-origin/channel adapter
3. Controller safety (B05–B06/B14/B17) — immutable generation, guarded render/export, worker-owned cache
4. Meaningful comparison/search (B04/B08–B09/B12–B13/B15–B16)
5. Responsive extension UI (U01–U09, เลิก B18) — ขออนุมัติถ้า architectural
6. Release gate: regression + red tests green + native desktop/high-DPI + GL both paths + export reopen + EXE smoke

## ภาษาและข้อความ

เอกสาร/UI ภาษาไทย; ส่งต่อข้อกำหนดภาษาไทยใน spec เราอ่านได้ ต้องคงคำที่นักดนตรีคุ้น (IR, attack, palm mute, blend) และอธิบายตัวเลขเป็น character ไม่ใช่ผู้ชนะ
