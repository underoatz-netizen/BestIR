# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds a single-file BestIR.exe
#   python -m PyInstaller BestIR.spec --noconfirm

a = Analysis(
    ['bestir.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['sounddevice', 'soundfile'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BestIR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
