# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - KDRG V4.7 코드 관계 검색기 Windows GUI exe.

로컬 실행:
    pyinstaller kdrg.spec

build_windows.bat / GitHub Actions workflow가 이 spec 파일을 그대로 사용합니다.
버전/파일명은 version.py 한 곳에서만 관리합니다.
"""

from PyInstaller.utils.hooks import collect_all

import version as _version

block_cipher = None

# PySide6는 Qt 플랫폼 플러그인(qwindows.dll 등)과 리소스가 별도 폴더에 있어
# --add-data만으로는 누락되기 쉬우므로 collect_all로 전부 수집합니다.
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all("PySide6")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=pyside6_binaries,
    datas=pyside6_datas
    + [
        ("data/kdrg_v47_ui_fixture.json", "data"),
    ],
    hiddenimports=pyside6_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_version.APP_NAME + "_" + _version.APP_VERSION,
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
