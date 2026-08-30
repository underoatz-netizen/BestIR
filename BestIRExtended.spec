# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds the EXTENDED single-file executable.
#   python -m PyInstaller BestIRExtended.spec --noconfirm
# The legacy BestIR.spec / BestIR.exe remain untouched.

a = Analysis(
    ['bestir_extended.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['sounddevice', 'soundfile', 'app.extensions',
                   'app.extensions.ui'],
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
    name='BestIRExtended',
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
