# BestIR — คัดกรอง IR อัตโนมัติ

แอป desktop (Windows) สำหรับโหลดไฟล์ IR (Impulse Response) ทั้งโฟลเดอร์ เพื่อ **วิเคราะห์โทนอัตโนมัติ → คัดกรอง/จัดอันดับตามโทนที่ต้องการ → ฟัง A/B ในแอป → ส่งออกไฟล์ที่รอด** — เหมาะกับ workflow ที่เริ่ม sound signal chain จาก IR ก่อนเลือก amp

## เริ่มใช้งาน

### วิ่งจากซอร์ส (ต้องมี Python 3.12+)
```bat
pip install -r requirements.txt
run.bat
```

### ใช้ไฟล์ .exe
สั่ง build ครั้งเดียว:
```bat
pip install pyinstaller
python -m PyInstaller BestIR.spec --noconfirm
```
แล้วเอา `dist\BestIR.exe` ไปใช้ได้เลย (ไม่ต้องติดตั้ง Python)

## วิธีใช้งาน

1. **Add Folder…** — เลือกโฟลเดอร์ IR (สแกน recursive รองรับ wav/flac/aiff, mono/stereo ทุก sample rate) ไฟล์จะถูกวิเคราะห์และเก็บ cache ไว้ รอบหน้าสแกนไวมาก
2. ตารางซ้ายแสดงทุกไฟล์พร้อมเมตริก — ใช้ **Search / SR / Ch / Tags / Flat ≤** กรอง
3. เลือกโทนที่ต้องการในแผงล่าง:
   - **Preset** — Flat / Bright / Dark / Scooped / Mid-forward / Tight low / Vintage
   - **Bands** — สไลเดอร์ 7 ย่าน (Sub…Air) หน่วย dB
   - **Reference** — เลือก IR ที่ชอบในตาราง แล้วกด **Use as Reference** ทางขวา เพื่อหา IR ที่โทนใกล้เคียง
4. กด **Rank** (หรือ `Ctrl+R`) — ตารางจะเรียงตามความใกล้เคียง target (หน่วย dB RMS, แถว Top-N ไฮไลต์สีเขียว) และกราฟไฮไลต์ Top-N ให้ด้วย
5. คลิกแถวเพื่อดูรายละเอียด (band bars, peak/notch, waveform) และ **Play** เพื่อฟัง IR ผ่านสัญญาณทดสอบ (pink noise / DI power chord / palm mute / ไฟล์ WAV ของคุณเอง)
   - **A/B ◀ ▶** สลับฟัง IR ถัดไป/ก่อนหน้าในลิสต์ที่กรองไว้ (หรือกด Space)
   - **Level match** ปรับความดังเท่ากันอัตโนมัติ กันหูถูกหลอกว่า "ดังกว่า = ดีกว่า"
6. เลือกแถวที่รอด (Ctrl+คลิก หลายแถว) → **Export Selected…** หรือ **Export Top-N…** เพื่อ copy ไฟล์ไปโฟลเดอร์ใหม่

## Tone Match — หา IR ให้เข้ากับ signal chain ของคุณ

แท็บ **Tone Match** คือ workflow ออกแบบมาเพื่อคำถามว่า *"DI กีตาร์ของผม + IR ตัวไหน = โทนที่ผมอยากได้"*

1. **อัด DI** — กด `● Record DI` แล้วเล่น riff เปล่า ๆ 10–20 วินาที (ปรับความยาวได้ 5–60 วิ) หรือ `Load DI WAV…` ถ้ามีไฟล์อยู่แล้ว
2. **เช็ค Tone** — แอปวิเคราะห์ DI ทันทีเป็น **Tone Ref** (tilt, flatness, จุด peak ของ pickup) แสดงในแท็บและเป็นเส้นเหลืองบนกราฟ
3. **เลือกโทน output ที่อยากได้** — Balanced (แบน) / Bright / Dark / Scooped / … หรือ `Match WAV tone…` (เอาเพลง/เดโม่ที่ชอบมาเป็นเป้าหมาย)
4. **ระบบคัด Tone-Matching IR** — กด `Rank` ระบบจะคำนวณ *needed IR curve* = `output ที่อยากได้ − DI tone` แล้วจัดอันดับ IR ที่แมสนั้นได้ที่สุด (เส้นประสีส้มบนกราฟคือ "IR ที่คุณต้องการ")
5. **ดู EQ ของ IR + EQ output สุดท้าย** — คลิก IR ตัวไหนก็ได้ เส้นเขียว = EQ ของ IR, เส้นฟ้า = **EQ ของ output จริง** (DI + IR) พร้อมข้อความบอกระยะห่างจาก target และ tilt ของ output
6. **ฟังผลลัพธ์** — ใน Audition เลือก Source เป็น `Recorded DI` แล้วกด Play จะได้ยิน DI ของคุณผ่าน IR ตัวนั้นจริง ๆ (A/B ◀ ▶ สลับเทียบได้)

> หลักการ: magnitude ของการ convolve = ผลบวกของ magnitude (dB) พอดี ระบบจึง "ทำนาย" EQ ของ output ได้แม่นโดยไม่ต้องเรนเดอร์เสียง (ตรวจสอบแล้วต่างจาก convolution จริง < 0.5 dB)


> คลิกบนเส้นกราฟเพื่อเลือก IR นั้นได้เลย / ชี้เมาส์เพื่อดูชื่อไฟล์

## เมตริกที่แอปวัด

ทุก IR ถูก normalize ที่ย่านหลัก 80 Hz–8 kHz (จุด 0 dB = ค่าเฉลี่ยย่านหลัก) แล้ววัด:

| เมตริก | ความหมาย |
|---|---|
| Flat | ค่าเบี่ยงเฉลี่ยจากแบน (dB) ช่วง 80 Hz–8 kHz — ยิ่งต่ำยิ่ง flat |
| Tilt | ความชัน (dB/octave) 200 Hz–8 kHz — บวก = bright, ลบ = dark |
| Sub…Air | ระดับเฉลี่ยแต่ละย่าน (dB เทียบจุด 0) |
| Peak / Notch | จุด resonant โดด/บุ๋มที่แรงที่สุด (เทียบเส้น smooth 1-octave) |
| Len ms | ความยาวที่ได้ยินจริง (onset → −60 dB) |

**Tags** อย่าง Bright/Dark/Scooped/Boomy/Thin/Fizzy ถูกสรุปโดยเทียบกับ median ของ library ทั้งหมด (ไลบรารีน้อยกว่า 20 ไฟล์ใช้เกณฑ์สัมบูรณ์) จึงแยกแยะภายใน pack เดียวกันได้

## คำสั่งอื่น

```bash
# วิเคราะห์ผ่าน command line ดูตารางเมตริก
python -m app.smoke "E:\path\to\IRs"

# รัน unit tests
python -m pytest tests/ -q

# selftest (ไม่เปิดหน้าจอ)
python -m app.main --selftest
```

## โครงสร้าง

```
app/core/   audio_io, analysis (DSP), matching, presets, cache, scanner, audition, exporter, tonematch
app/ui/     model, library_panel, plot_panel, screen_panel, inspector_panel, main_window, workers
tests/      unit tests + offscreen GUI smoke test (ครอบ DI/tone-match workflow)
```

Cache: `%LOCALAPPDATA%\BestIR\cache.json` (ตรวจจาก mtime+size — แก้ไฟล์ IR แล้วจะถูกวิเคราะห์ใหม่เอง)
