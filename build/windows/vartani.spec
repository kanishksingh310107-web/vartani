# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
hidden = [
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
    "multipart", "multipart.multipart", "uvicorn.logging", "uvicorn.loops.auto",
    "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.off", "h11",
]
hidden += collect_submodules("indic_transliteration")
datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "data" / "starter"), "data/starter"),
    (str(ROOT / "data" / "paper"), "data/paper"),
]
datas += collect_data_files("indic_transliteration")

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "transformers", "accelerate", "faster_whisper", "ctranslate2"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vartani",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Vartani",
)
