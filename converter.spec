# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec для сборки портативного ImageConverter.exe

block_cipher = None

a = Analysis(
    ["converter_gui.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pillow_heif",
        "PIL._tkinter_finder",
        "PIL.Image",
        "PIL.ImageTk",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ImageConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # сжать exe (требует UPX, опционально)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # без консольного окна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",  # раскомментируй если добавишь иконку
)
