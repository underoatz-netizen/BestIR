# WP-09 QA Record — Extended build

**Date:** 2026-08-30 · **Build:** `dist\BestIRExtended.exe` (onefile, ~101 MB)

## Test gates (all pass)

- Legacy suite: `python -m pytest tests -q -p no:cacheprovider` → **84 passed**
  (20 legacy + 64 extension tests)
- `python -m app.main --selftest` → OK
- `python -m app.extended_main --selftest` → OK (same DSP selftest)
- Legacy offscreen GUI smoke (`tests/gui_smoke.py`) → pass
- Extended offscreen GUI smoke (`tests/extensions/extended_gui_smoke.py`) →
  library scan, workbench A/B, pair pipeline, CSD/spectrogram tabs,
  response search (2 eligible), screenshot — all without audio devices

## Benchmarks (382-file library, cached legacy scan)

| Operation | Measured |
|---|---|
| Legacy tone scan (Tier 0, cached) | 0.23 s total — extension adds **zero** scan cost |
| Response fingerprint (Tier 1) cold | ~73–81 ms/file (background worker) |
| Response fingerprint cached | 0.12 ms/file |
| A/B matrices CSD+spectrogram+phase (Tier 2) | ~45 ms |
| Pair comparison + blend prediction | ~12 ms |

## Packaging

- `BestIR.exe` — legacy build from `BestIR.spec` — untouched
- `BestIRExtended.exe` — extended build from `BestIRExtended.spec`
  (entry `bestir_extended.py`, hidden imports: sounddevice, soundfile,
  app.extensions*)
- Default launcher stays `BestIR.exe` per plan §12 (switching requires a
  separate owner-approved change)

## Known notes

- OpenGL CSD surface is optional: PyOpenGL/pyqtgraph.opengl not bundled;
  the deterministic 2D heatmap + stacked-ridge fallback renders instead
  (renderer interface `app/extensions/ui/renderers/`).
- WP-08 (processing/export of modified IRs) intentionally deferred per plan
  §12 — lower priority than compare/matching; analysis never mutates audio.
- External UIA automation probes were observed to occasionally terminate the
  frozen exe during QA; normal mouse/keyboard use is unaffected.

## WP-08 addendum (implemented after owner request, 2026-08-30)

- `app/extensions/processing.py` — fractional delay (zero-padded FFT ramp),
  polarity, optional peak normalization, aligned blend sum
- `app/extensions/processing_export.py` — Export B (aligned) / Blend WAV /
  provenance JSON; collision-safe naming, atomic writes (tmp + os.replace),
  parent-dir auto-create; sources never modified (verified by test)
- UI: Export group in the Compare A/B "Phase & Blend" tab — populated only
  from an explicit button press (plan §12 requirement)
- Tests: +9 (total suite 93 passed), incl. delay round trip ≤ 0.25 sample
  after alignment, collision safety, source immutability, JSON provenance
- Bug fix found by the extended smoke: worker DSP calls were missing the
  config argument (pair/spectrogram/CSD tabs appeared empty); the smoke now
  exercises the real worker pipeline instead of calling DSP directly

## Wave 8 QA addendum (2026-09-03)

- Full automated suite: baseline **236 passed** twice consecutively (32.93 s and 33.08 s); after the async-export regression test, `python -m pytest tests -q --basetemp=... -p no:cacheprovider` → **237 passed** (33.12 s).
- Selftests: `python -m app.main --selftest` and `python -m app.extended_main --selftest` → OK.
- Export hardening: atomic filename reservation, temporary-file cleanup, PCM clipping/headroom guard and pair validation. Aligned-B, blend and report export preparation/I/O run in a single-flight background worker so the GUI remains responsive for large files.
- Remaining release gate is physical-environment QA only: native Windows DPI/keyboard, real audio playback/re-amping, OpenGL GPU rendering, and packaged `BestIR.exe` / `BestIRExtended.exe` build and smoke. These are not covered by offscreen automated tests and remain NOT RUN.

## Native QA update (2026-09-03)

- Keyboard navigation and real audio playback/re-amping passed. `BestIRExtended.exe` smoke passed.
- DPI 125% and 150% passed. At 175%, some controls disappear; 200% was not available on the test display. Compare A/B Workbench overflows at 125-175% because it lacks a full-screen/maximize path. This is a release blocker.
- Compare A/B was retested after its containment fix and is scrollable/complete at 120%, 150%, and 175%. The main window remains a blocker above 120%: Library overlaps the centre/Audition is vertically compressed at 150%; the right zone disappears with no scrollbars at 175%. This main-window work is outside the approved Compare-only scope.
- Fixed a P1 lifecycle issue where the "Desired Response" frame appeared as a new top-level popup each time Compare A/B opened. It is now embedded in Response Search's control card and has a regression test.
- Both PyInstaller builds completed, but `PyOpenGL` is not installed (`ModuleNotFoundError: No module named 'OpenGL'`), so the packaged build validates only the 2D CSD fallback. OpenGL 3D GPU validation remains blocked.
- Release decision: ship the deterministic 2D CSD fallback only. OpenGL 3D is deferred and removed from this release's QA gate; it requires a separately packaged dependency and real-GPU validation before any future enablement.
