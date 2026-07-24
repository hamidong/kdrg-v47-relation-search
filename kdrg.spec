# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()
VERSION_FILE = ROOT / "version.py"

version_values = runpy.run_path(str(VERSION_FILE)) if VERSION_FILE.exists() else {}
configured_exe_name = str(
    version_values.get("EXE_NAME")
    or "KDRG_V47_Relation_Search.exe"
)
bundle_name = Path(configured_exe_name).stem

integrated_json = ROOT / "data" / "kdrg_v47_search_integrated.json"
if not integrated_json.is_file():
    raise FileNotFoundError(
        f"필수 runtime 데이터가 없습니다: {integrated_json}"
    )

hiddenimports = sorted(
    set(
        collect_submodules("app")
        + [
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
        ]
    )
)

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(integrated_json), "data"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=bundle_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
