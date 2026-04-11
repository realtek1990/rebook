# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ReBook macOS — self-contained .app bundle."""
import os
import sys

block_cipher = None

APP_DIR = os.path.join('ReBook.app', 'Contents', 'Resources', 'app')

a = Analysis(
    [os.path.join(APP_DIR, 'native_gui.py')],
    pathex=[APP_DIR],
    binaries=[],
    datas=[
        # App data files
        (os.path.join(APP_DIR, 'static'), 'static'),
    ],
    hiddenimports=[
        # ── PyObjC ────────────────────────────────────────────────
        'objc',
        'AppKit',
        'Foundation',
        'PyObjCTools',
        'PyObjCTools.AppHelper',

        # ── App modules (same directory, imported by name) ───────
        'i18n',
        'corrector',
        'converter',
        'tts_engine',
        'image_translator',

        # ── Core deps ────────────────────────────────────────────
        'litellm',
        'litellm.llms',
        'litellm.llms.openai',
        'litellm.llms.openai.chat',
        'litellm.main',
        'markdown',
        'ebooklib',
        'ebooklib.epub',
        'ebooklib.utils',
        'pymupdf',
        'fitz',
        'bs4',
        'markdownify',
        'google.genai',
        'google.genai.types',
        'PIL',
        'PIL.Image',
        'edge_tts',
        'edge_tts.communicate',

        # ── Networking (used by litellm/google-genai) ────────────
        'httpx',
        'httpcore',
        'anyio',
        'certifi',
        'h11',
        'aiohttp',
        'aiosignal',

        # ── email (for Kindle send) ──────────────────────────────
        'smtplib',
        'email',
        'email.message',

        # ── stdlib needed by edge-tts ────────────────────────────
        'asyncio',
        'json',
        'xml',
        'xml.etree',
        'xml.etree.ElementTree',
        'html.parser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy/unnecessary packages
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'torch',
        'torchvision',
        'torchaudio',
        'transformers',
        'tensorflow',
        'keras',
        'sklearn',
        'cv2',
        'PIL.ImageTk',
        'tkinter',
        'marker_pdf',
        'marker',
        'surya',
        'jupyterlab',
        'notebook',
        'IPython',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ReBook',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # No terminal window
    target_arch=None,           # Native arch (arm64 on Apple Silicon)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='ReBook',
)

app = BUNDLE(
    coll,
    name='ReBook.app',
    icon='ReBook.app/Contents/Resources/AppIcon.icns',
    bundle_identifier='com.rebook.app',
    info_plist={
        'CFBundleName': 'ReBook',
        'CFBundleDisplayName': 'ReBook',
        'CFBundleShortVersionString': '3.12.2',
        'CFBundleVersion': '3.12.2',
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'PDF Document',
                'CFBundleTypeExtensions': ['pdf'],
                'CFBundleTypeRole': 'Viewer',
            },
            {
                'CFBundleTypeName': 'EPUB Document',
                'CFBundleTypeExtensions': ['epub'],
                'CFBundleTypeRole': 'Editor',
            },
            {
                'CFBundleTypeName': 'Markdown Document',
                'CFBundleTypeExtensions': ['md'],
                'CFBundleTypeRole': 'Viewer',
            },
        ],
    },
)
