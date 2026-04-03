# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ReBook Windows."""

import os

block_cipher = None
APP_DIR = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(APP_DIR, 'rebook_win.py')],
    pathex=[APP_DIR],
    binaries=[],
    datas=[
        # Include shared app files
        (os.path.join(APP_DIR, 'i18n.py'), '.'),
        (os.path.join(APP_DIR, 'converter.py'), '.'),
        (os.path.join(APP_DIR, 'corrector.py'), '.'),
        (os.path.join(APP_DIR, 'manual_convert.py'), '.'),
        (os.path.join(APP_DIR, 'requirements.txt'), '.'),
        (os.path.join(APP_DIR, 'icon.ico'), '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'tkinter',
        'json',
        'queue',
        'smtplib',
        'email',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'scipy', 'torch', 'PIL'],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ReBook',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(APP_DIR, 'icon.ico'),
)
