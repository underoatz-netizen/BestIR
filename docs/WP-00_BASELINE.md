# WP-00 Baseline Record

Date: 2026-08-30
Python: 3.14.6

- numpy 2.5.1
- scipy 1.18.0
- soundfile 0.14.0
- sounddevice 0.5.6
- pyqtgraph 0.14.0
- PySide6 6.11.2

## Checksums (sha256[:16]) — legacy protected files

```
e3b0c44298fc1c14  app/core\__init__.py
75f64f35991e84cb  app/core\analysis.py
58c8dbf9a6d163b0  app/core\audio_io.py
6ff0e289a296d139  app/core\audition.py
19afe0099b34df8c  app/core\cache.py
dcb487a2d2394a61  app/core\exporter.py
e043837bc6e8c1bc  app/core\matching.py
3610e8cb3a965114  app/core\presets.py
7322c1fcc6158109  app/core\scanner.py
77101456e0524f1b  app/core\tonematch.py
e3b0c44298fc1c14  app/ui\__init__.py
be7be06562c0d0f7  app/ui\inspector_panel.py
c2ef36ea7b651867  app/ui\library_panel.py
9490027c3772216f  app/ui\main_window.py
01c493289923fadd  app/ui\model.py
76ecf84d0465cff3  app/ui\plot_panel.py
d54e7041143a82c3  app/ui\screen_panel.py
1d18fa5c304c5bc4  app/ui\styles.py
0f52e1f2160e7af3  app/ui\workers.py
```

## Gate results

- `python -m pytest tests -q --basetemp=...wp00-full -p no:cacheprovider` -> 20 passed
- `python -m app.main --selftest` -> BestIR selftest OK
- Git initialized; baseline commit `269f84b`
