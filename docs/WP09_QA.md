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
