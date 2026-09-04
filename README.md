<div align="center">

# 🎸 BestIR Extended
### Guitar Cabinet Impulse Response Screener, Tone Match & Compare Workbench

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2064--bit-0078D6.svg)](https://www.microsoft.com/windows)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%7C%20PyQtGraph-41CD52.svg)](https://pyside.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*A precision desktop application for guitarists, audio engineers, and producers to organize, analyze, match, audition, and blend Impulse Responses (IR) with mathematical accuracy and musician-friendly feedback.*

[**🇹🇭 ภาษาไทย (Thai Manual)**](#-คู่มือการใช้งานภาษาไทย) | [**🇬🇧 English Manual**](#-english-user-manual)

---

</div>

## 📑 สารบัญ / Table of Contents
- [🇹🇭 คู่มือการใช้งานภาษาไทย](#-คู่มือการใช้งานภาษาไทย)
  - [1. บทนำและคุณสมบัติเด่น](#1-บทนำและคุณสมบัติเด่น)
  - [2. การติดตั้งและเปิดใช้งาน](#2-การติดตั้งและเปิดใช้งาน)
  - [3. หน้าต่างหลัก (Main Screener)](#3-หน้าต่างหลัก-main-screener)
  - [4. ระบบค้นหาและการคัดเกรด (Response Search)](#4-ระบบค้นหาและการคัดเกรด-response-search)
  - [5. โต๊ะเปรียบเทียบ A/B (Compare A/B Workbench)](#5-โต๊ะเปรียบเทียบ-ab-compare-ab-workbench)
  - [6. การผสมสัญญาณและการส่งออก (Phase & Blend Export)](#6-การผสมสัญญาณและการส่งออก-phase--blend-export)
- [🇬🇧 English User Manual](#-english-user-manual)
  - [1. Overview & Key Features](#1-overview--key-features)
  - [2. Installation & Quick Start](#2-installation--quick-start)
  - [3. Main Screener Interface](#3-main-screener-interface)
  - [4. Response-Aware Search & Presets](#4-response-aware-search--presets)
  - [5. Compare A/B Workbench](#5-compare-ab-workbench)
  - [6. Phase Alignment & Blend Export](#6-phase-alignment--blend-export)

---

# 🇹🇭 คู่มือการใช้งานภาษาไทย

## 1. บทนำและคุณสมบัติเด่น
**BestIR Extended** ออกแบบมาเพื่อแก้ปัญหา "IR Hoarding" ของมือกีตาร์และซาวด์เอ็นจิเนียร์ ที่มีไฟล์ IR สะสมนับพันไฟล์แต่เสียเวลาในการนั่งฟังทีละไฟล์ ระบบนี้ใช้ Digital Signal Processing (DSP) ในการถอดรหัสบุคลิกเสียง (Acoustic Fingerprint) เพื่อค้นหาและคัดกรองตัวที่ดีที่สุดอย่างรวดเร็ว

### คุณสมบัติเด่น:
- **Instant Tonal Fingerprinting:** วิเคราะห์ Spectral Balance (Low, Low-Mid, Mid, High, Air), ความแบนราบ (Flatness), และความเอียงของความถี่ (Spectral Tilt)
- **Acoustic Transient & Decay Analysis:** วัดความเร็วหัวโน้ต (Time to peak), พลังงานช่วงต้น (Early energy), ความหนาแน่นของเนื้อเสียง และการสลายตัวของย่านต่ำ (D20 Decay)
- **Intelligent Tone Matching:** ปรับจูนค้นหา IR ที่โทนใกล้เคียงกับ Reference Track หรือสัญญาณกีตาร์ DI
- **Compare A/B Workbench:** สลับฟัง A/B แบบไม่มีสะดุด และดูความต่างของเสียงที่อธิบายเป็น **"ภาษานักดนตรี"**
- **Phase & Blend Prediction:** ตรวจสอบการหักล้างของเฟส (Comb filtering) อัตโนมัติ พร้อมปรับชดเชยเวลา (Time delay) และขั้วสัญญาณ (Polarity) ให้ตรงกันก่อนผสมเสียง

---

## 2. การติดตั้งและเปิดใช้งาน
โปรแกรมถูกสร้างมาเป็น **Portable Executable** บน Windows 64-bit ไม่ต้องติดตั้งซอฟต์แวร์เสริม

1. ดาวน์โหลดไฟล์ `BestIRExtended.exe` จากโฟลเดอร์ `dist/` หรือหน้า Releases
2. ดับเบิลคลิกเปิดโปรแกรมได้ทันที
3. *(สำหรับนักพัฒนา)* รันผ่าน Source code:
   ```powershell
   python -m pip install -r requirements.txt
   python bestir_extended.py
   ```

---

## 3. หน้าต่างหลัก (Main Screener)

### 3.1 การจัดการคลังไฟล์ (Library Management)
- **Add Folder…:** เพิ่มโฟลเดอร์ที่เก็บไฟล์ IR (`.wav`) ระบบจะสแกนและแคชข้อมูลอัตโนมัติ
- **Remove Folder:** เลือกโฟลเดอร์ในรายการแล้วกดปุ่มนี้เพื่อนำโฟลเดอร์และรายการ IR ออกจากคลังทันที
- **Rescan (force):** สแกนไฟล์ทั้งหมดใหม่อีกครั้งเพื่ออัปเดตไฟล์ที่มีการเปลี่ยนแปลง

### 3.2 แถบตัวกรองและค้นหา (Filters Bar)
- **Search:** พิมพ์คำค้นหาชื่อไฟล์หรือตำแหน่งไมค์ (เช่น `57`, `CapEdge`, `Cone`)
- **SR / Ch:** กรองตาม Sample Rate (`44.1k`, `48k`, `96k`) หรือช่องสัญญาณ (`Mono` / `Stereo`)
- **Filters ▾:** แผงกรองพับเก็บได้ สำหรับเลือกแท็ก และกรองค่า Flatness

### 3.3 การจัดอันดับโทนเสียง (Tone Screener & Presets)
- เลือกพรีเซ็ตเป้าหมายที่ต้องการ เช่น:
  - `Flat`: โทนสมดุล ไม่มีย่านใดยื่นล้ำ
  - `Tight low`: ตัดย่านบวมต่ำกว่า 100 Hz สำหรับเสียงแตกริฟฟ์เร็ว (Fast chugs)
  - `Mid-forward`: ชูย่านกลาง ดันโซโล่ให้ทะลุมิกซ์
  - `Scooped`: เว้ากลาง หนักหัว-ท้าย สไตล์โมเดิร์นเมทัล
- กด **`Rank`** ระบบจะเรียงลำดับ IR จากทั้งคลังที่ใกล้เคียงกับพรีเซ็ตที่สุดขึ้นมาอันดับต้นๆ ทันที

### 3.4 เครื่องเล่นทดลองฟัง (Audition Engine)
- กด **Spacebar** หรือปุ่ม **`Play`** เพื่อฟังเสียง
- สลับสัญญาณ Source ได้ระหว่าง Pink Noise หรือคลิก **`Load…`** เพื่อใส่ไฟล์กีตาร์แห้ง (Clean DI track)
- ปุ่ม **`Level match`** ช่วยควบคุมระดับความดังของทุก IR ให้เท่ากันขณะสลับฟัง ป้องกันอาการหูหลอก (Loudness bias)

---

## 4. ระบบค้นหาและการคัดเกรด (Response Search)
กดปุ่ม **`Response Search`** ที่แถบเครื่องมือด้านบน เพื่อค้นหา IR ตามลักษณะทางกายภาพของเสียง:
- **Simple Mode:** กำหนดเป้าหมายการตอบสนองที่ต้องการโดยตรง:
  - *Low-end D20 target (ms):* กำหนดความสั้น-ยาวของหางเบส (เหมาะกับเลือกระหว่างกีตาร์ริธึ่มแน่นๆ กับโซโล่ฉ่ำๆ)
  - *Fast attack target (ms):* กำหนดความกระชับของหัวโน้ต
  - *Boxiness target (dB):* ควบคุมระดับความอู้เป็นกล่องของตู้ลำโพง
- **Advanced Mode:** ปรับน้ำหนักคะแนน (Weights) แต่ละย่านความถี่ และกำหนดนโยบาย Missing metric policy

---

## 5. โต๊ะเปรียบเทียบ A/B (Compare A/B Workbench)
เลือก IR 2 ตัวในตาราง แล้วกดปุ่ม **`Compare A/B`**:

### 5.1 ส่วนหัว Dual-Deck Header
- แสดงชื่อไฟล์ IR A (สีฟ้า Electric Cyan) และ IR B (สีเขียว Neon Emerald)
- ปุ่ม **`⇄`** สลับ IR ฝั่ง A และ B ทันที
- แถบเลื่อนแนวนอนอัตโนมัติ ไม่บังคับให้หน้าต่างล้นจอเมื่อชื่อไฟล์ยาว

### 5.2 แท็บการวิเคราะห์ทั้ง 5 ด้าน
1. **📊 Summary (สรุปสำหรับนักดนตรี):**
   - **จุดต่างที่ควรลองฟัง (A/B):** สรุปเปรียบเทียบลักษณะเสียงสั้นกระชับเข้าใจง่าย
     - ⚡ *หัวโน้ต*: ระบุฝั่งที่หัวโน้ตพุ่งไวกว่า หรือมีพลังงานช่วงต้นชัดเจน
     - ⌛ *หางเสียงเบส*: ระบุฝั่งที่ย่านต่ำเก็บตัวไวกว่าหรือค้างนานกว่า
     - ▣ *ความอู้/กลางต่ำ*: ระบุฝั่งที่มีย่านกลางต่ำค้างเด่น (หนาขึ้นหรืออาจจะอู้)
     - ↔ *เวลาตอบสนอง*: ระบุย่านความถี่ที่มีการหน่วงเวลาต่างกัน
   - ตารางตัวเลขเปรียบเทียบละเอียด (dB, ms, %) สำหรับใช้อ้างอิงทางเทคนิค
2. **📈 Waveform & Envelope:** แสดงรูปคลื่น Impulse และ Envelope สันโค้งพลังงาน พร้อมจุด Marker บอก Onset Peak
3. **🌊 CSD Waterfall:** พล็อต Waterfall แสดงการสลายตัวของพลังงานตามกาลเวลา (Cumulative Spectral Decay) พร้อมตัววัด D10, D20, D30 แยกแต่ละย่าน
4. **🔥 Spectrogram Heatmaps:** แผนที่ความร้อนเปรียบเทียบ Spectral Density และแสดงผลต่าง (Difference Map)
5. **⚡ Phase & Blend Prediction:** วิเคราะห์เฟสและความเข้ากันได้ (รายละเอียดในข้อ 6)

---

## 6. การผสมสัญญาณและการส่งออก (Phase & Blend Export)

### 6.1 ระบบจัดเฟสและพรีวิว (Phase Alignment Engine)
- ระบบจะคำนวณหาความต่างของเวลาที่แม่นยำระดับเสี้ยวตัวอย่าง (Fractional delay samples) และตรวจจับขั้วสัญญาณ (+/-)
- มีป้ายแจ้งเตือน **Comb Risk Alert**:
  - `✓ Safe`: เฟสเข้ากันได้ดี ผสมแล้วเสียงหนาแน่นขึ้น
  - `⚠ Medium`: มีการหักล้างในบางย่านความถี่
  - `✕ High`: มี Phase Cancellation รุนแรง (เสี่ยงเกิดเสียงกระป๋องหรือเบสหาย)
- ตัวเลื่อน **Blend Ratio (0% - 100% B)**: เลื่อนเพื่อพรีวิวกราฟเสียงที่จะได้จากการผสมแบบเรียลไทม์

### 6.2 การส่งออกไฟล์แบบ Non-destructive
ปุ่ม Export จะปลดล็อกให้ใช้งานเมื่อสัญญาณทั้งสองผ่านการวิเคราะห์สมบูรณ์:
- **`Export B (aligned)`**: สร้างไฟล์ WAV ของ IR B ที่ถูกเลื่อนเวลาและกลับเฟสให้ตรงกับ IR A เรียบร้อยแล้ว (นำไปใช้คู่กับ A ใน Multi-mic setup ได้ทันทีโดยไม่บวมเฟส)
- **`Export Blend WAV`**: รวมเสียง IR A + B ตามอัตราส่วนที่เลือกบน Blend slider ออกมาเป็นไฟล์ IR สำเร็จรูป
- **`Export Report (JSON)`**: ส่งออกรายงานทางเทคนิค เก็บค่าสถิติ, ค่าหน่วงเวลา, และ Checksum ของคู่สัญญาณไว้ตรวจสอบย้อนหลัง

---
---

# 🇬🇧 English User Manual

## 1. Overview & Key Features
**BestIR Extended** solves "IR Hoarding" syndrome. Instead of spending hours auditioning thousands of cabinet impulse response WAV files, BestIR extracts acoustic and spectral fingerprints using advanced Digital Signal Processing (DSP) to rank, inspect, match, and blend IRs mathematically and intuitively.

### Core Capabilities:
- **Tonal Fingerprinting:** Automated quantification of 5 spectral sub-bands (Low, Low-Mid, Mid, Mid-High, Air), spectral flatness, and dB/octave tilt.
- **Transient & Temporal Dynamics:** Micro-timing analysis including Time-to-Peak, Rise Time (10-90%), Early Energy Ratio (0-5ms), Crest Factor, and Low-frequency decay ($D_{20}$).
- **Curve-Match Ranking:** Instant scoring against musical target presets or external clean DI recordings.
- **Compare A/B Workbench:** Gapless dual-deck auditioning with concise, **musician-focused acoustic difference explanations**.
- **Phase & Blend Engine:** Automated fractional-sample cross-correlation alignment, polarity detection, comb-risk scoring, and atomic WAV export.

---

## 2. Installation & Quick Start
Packaged as a standalone Windows 64-bit portable binary with zero external dependencies.

1. Download `BestIRExtended.exe` from `dist/` or GitHub Releases.
2. Launch the application by double-clicking.
3. *(Developers)* Run from source:
   ```powershell
   python -m pip install -r requirements.txt
   python bestir_extended.py
   ```

---

## 3. Main Screener Interface

### 3.1 Folder Management
- **Add Folder…:** Select directories containing `.wav` impulse responses. Background workers scan, fingerprint, and persist them in a local cache.
- **Remove Folder:** Select one or more folders from the list and click to prune them from the library and in-memory table immediately.
- **Rescan (force):** Invalidates the cache and re-analyzes all files under configured roots.

### 3.2 Filtering & Searching
- **Search:** Instant substring filter across file paths and mic naming conventions.
- **SR / Ch:** Filter by Sample Rate (`44.1k`, `48k`, `96k`) or Channel count (`Mono` / `Stereo`).
- **Filters ▾:** Expandable drawer for checkable tags and maximum flatness constraints.

### 3.3 Tonal Screener & Target Presets
Select an acoustic target curve to rank your library:
- `Flat`: Linear, unhyped reference balance across 80 Hz - 8 kHz.
- `Tight Low`: High-pass slope below 100 Hz engineered for fast palm-muted rhythm riffs.
- `Mid-forward`: Enhanced vocal-range midrange to punch solo lines through dense mixes.
- `Scooped`: Aggressive V-shape curve tailored for modern heavy metal.
Click **`Rank`** to sort the entire library by shape similarity (RMS error score, lower = closer).

### 3.4 Auditioning Engine
- Press **Spacebar** or click **`Play`** to audition the selected row.
- Toggle between synthetic Pink Noise or click **`Load…`** to feed your own DI guitar tracks.
- Enable **`Level match`** to normalize playback levels dynamically, eliminating perceptual volume bias.

---

## 4. Response-Aware Search & Presets
Click **`Response Search`** on the main toolbar to filter candidates using physical response criteria:
- **Simple Mode:** Focus directly on desired acoustic outcomes:
  - *Low-end D20 target (ms):* Desired bass decay duration.
  - *Fast attack target (ms):* Onset transient snap.
  - *Boxiness target (dB):* Resonance persistence in the low-mid spectrum.
- **Advanced Mode:** Expose custom objective weights and missing-metric rejection policies.

---

## 5. Compare A/B Workbench
Select two records in the library table and click **`Compare A/B`**:

### 5.1 Dual-Deck Header
- Clear slot distinction: **IR A** (Electric Cyan) and **IR B** (Neon Emerald).
- Click **`⇄`** to swap IR A and IR B instantaneously.
- Horizontally scrollable container ensures zero window overflow on high-DPI displays (120% – 175%).

### 5.2 Five Analysis Tabs
1. **📊 Summary (Musician-Friendly):**
   - **Key Differences Breakdown:** Clear, actionable bullets:
     - ⚡ *Attack & Snap*: Pinpoints which IR possesses a faster onset or punchier early energy.
     - ⌛ *Low Decay*: Explains which IR tightens up bass faster vs. sustains longer.
     - ▣ *Boxiness / Body*: Identifies resonant buildup in the lower midrange.
     - ↔ *Time Response*: Highlights differential group delay across specific frequency bands.
   - Comprehensive numerical evidence table ($dB$, $ms$, $\%$) accessible on the left.
2. **📈 Waveform & Envelope:** Signed sample plots, Hilbert envelope curves, and onset peak markers.
3. **🌊 CSD Waterfall:** Cumulative Spectral Decay heatmap displaying $D_{10}$, $D_{20}$, and $D_{30}$ decay metrics.
4. **🔥 Spectrogram Heatmaps:** Time-frequency spectral density plots with normalized difference maps.
5. **⚡ Phase & Blend Prediction:** Phase curves, group delay, and blend prediction (details below).

---

## 6. Phase Alignment & Blend Export

### 6.1 Alignment & Risk Mitigation
- Automated cross-correlation estimates native time delay ($\tau$ samples) down to sub-sample precision and detects phase inversion.
- **Comb Risk Chip:**
  - `✓ Comb Risk: Safe`: Minimal phase cancellation across the critical acoustic band.
  - `⚠ Comb Risk: Medium`: Noticeable cancellation notches present at specific frequencies.
  - `✕ Comb Risk: High`: Severe phase cancellation (comb filtering will hollow out tone and eliminate bass punch).
- **Blend Slider (0% - 100% B):** Interactive slider updating predicted frequency response in real time.

### 6.2 Non-Destructive Export Options
Source files remain strictly read-only. Export buttons become enabled once pair verification succeeds:
- **`Export B (aligned)`:** Produces a copy of IR B advanced by fractional delay and polarity-corrected to match IR A perfectly (ideal for multi-mic cabinet setups).
- **`Export Blend WAV`:** Exports the composite $A + B$ audio mix according to the current blend ratio slider.
- **`Export Report (JSON)`:** Exports full measurement metadata, checksums, delays, and acoustic metrics for auditing and record-keeping.

---

## 🛠 Tech Stack & Dependencies
- **Core:** Python 3.12+ / 3.14 compatible, NumPy, SciPy (Signal processing, FFT, Hilbert transform, cross-correlation)
- **Audio I/O:** `soundfile` (libsndfile backend), `sounddevice` (PortAudio backend)
- **GUI Engine:** `PySide6` (Qt for Python), `pyqtgraph` (Hardware-accelerated real-time plotting)
- **Design System:** Custom tactile **Boro UI** design tokens (Obsidian chassis, Boro Honey Gold accents, Electric Cyan & Neon Emerald channels)

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
