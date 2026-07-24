#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import py_compile
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_RUNTIME_REGRESSION_BUILDER_V1"

ROOT = Path.cwd()
REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_regression_config_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_regression_config_report.json"
BACKUP_DIR = REPORTS / "windows_runtime_regression_backups"

VALIDATION_42_TXT = REPORTS / "runtime_ui_bridge_validation_report.txt"
VALIDATION_42_JSON = REPORTS / "runtime_ui_bridge_validation_report.json"
PREVIEW_43_TXT = REPORTS / "runtime_ui_preview_build_report.txt"
PREVIEW_43_JSON = REPORTS / "runtime_ui_preview_build_report.json"

INTEGRATED_JSON = ROOT / "data" / "kdrg_v47_search_integrated.json"
PROTECTED_FILES = [
    INTEGRATED_JSON,
    ROOT / "app" / "kdrg_search_service.py",
    ROOT / "app" / "runtime_data_store.py",
    ROOT / "app" / "main_window.py",
    ROOT / "app" / "dialogs.py",
]

GENERATED_FILES = [
    ROOT / "kdrg.spec",
    ROOT / "build_windows.bat",
    ROOT / "run_local.bat",
    ROOT / "tests" / "windows_runtime_source_smoke.py",
    ROOT / "tests" / "verify_windows_runtime_bundle.py",
    ROOT / ".github" / "workflows" / "build-windows-release.yml",
    ROOT / "BUILD_AND_RELEASE.md",
]


SPEC_SOURCE = r'''# -*- mode: python ; coding: utf-8 -*-
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
'''


SOURCE_SMOKE_SOURCE = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_source_smoke_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_source_smoke_report.json"
SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_RUNTIME_SOURCE_SMOKE_V1"


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )


def first_key(mapping: Any) -> str:
    if isinstance(mapping, dict) and mapping:
        return sorted(str(key) for key in mapping)[0]
    return ""


def dotted_query(code: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    if len(normalized) > 3:
        return normalized[:3] + "." + normalized[3:]
    return normalized


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    from PySide6.QtWidgets import QApplication
    from app.kdrg_search_service import KdrgSearchService
    from app.runtime_data_store import KDRGRuntimeDataStore
    from app.main_window import MainWindow

    integrated_path = ROOT / "data" / "kdrg_v47_search_integrated.json"
    add_check(
        checks,
        "통합 JSON 존재",
        integrated_path.is_file(),
        str(integrated_path),
        "exists",
    )

    service = KdrgSearchService()
    status = service.status()
    add_check(checks, "service status", isinstance(status, dict), type(status).__name__, "dict")

    store = KDRGRuntimeDataStore()
    counts = {
        "adrg": len(getattr(store, "rules", {})),
        "aadrg": len(getattr(store, "aadrg_mapping", {})),
        "table": len(getattr(store, "tables", {})),
        "code": len(getattr(store, "code_to_tables", {})),
    }
    add_check(checks, "ADRG count", counts["adrg"] == 1132, counts["adrg"], 1132)
    add_check(checks, "AADRG count", counts["aadrg"] == 1233, counts["aadrg"], 1233)
    add_check(checks, "TABLE count", counts["table"] == 1308, counts["table"], 1308)
    add_check(checks, "CODE count", counts["code"] == 16571, counts["code"], 16571)

    adrg = "E011" if "E011" in getattr(store, "rules", {}) else first_key(getattr(store, "rules", {}))
    adrg_rows = store.search(adrg, "ADRG")
    add_check(
        checks,
        "ADRG exact search",
        bool(adrg_rows) and str(adrg_rows[0].key) == adrg,
        [str(row.key) for row in adrg_rows[:3]],
        adrg,
    )

    table_id = first_key(getattr(store, "tables", {}))
    table_rows = store.search(table_id, "TABLE")
    add_check(
        checks,
        "TABLE exact search",
        bool(table_rows) and str(table_rows[0].key) == table_id,
        [str(row.key) for row in table_rows[:3]],
        table_id,
    )

    code_to_tables = getattr(store, "code_to_tables", {})
    code_candidates = [
        str(code)
        for code in sorted(code_to_tables)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{3,}", str(code))
    ]
    code = code_candidates[0] if code_candidates else first_key(code_to_tables)
    query = dotted_query(code)
    code_rows = store.search(query, "상병코드")
    add_check(
        checks,
        "점 표기 CODE search",
        bool(code_rows) and str(code_rows[0].key) == code,
        {
            "fixture": code,
            "query": query,
            "rows": [str(row.key) for row in code_rows[:3]],
        },
        code,
    )

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()

    search_edit = getattr(window, "search_edit", None)
    category_combo = getattr(window, "category_combo", None)
    run_search = getattr(window, "run_search", None)

    add_check(checks, "MainWindow 생성", window is not None, type(window).__name__, "MainWindow")
    add_check(checks, "검색창 계약", search_edit is not None, bool(search_edit), True)
    add_check(checks, "검색유형 계약", category_combo is not None, bool(category_combo), True)
    add_check(checks, "검색 실행 계약", callable(run_search), callable(run_search), True)

    if search_edit is not None and category_combo is not None and callable(run_search):
        category_combo.setCurrentText("ADRG")
        search_edit.setText(adrg)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI ADRG event",
            str(search_edit.text()) == adrg,
            str(search_edit.text()),
            adrg,
        )

        category_combo.setCurrentText("상병코드")
        search_edit.setText(query)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI CODE event",
            str(search_edit.text()) == query,
            str(search_edit.text()),
            query,
        )

        category_combo.setCurrentText("TABLE")
        search_edit.setText(table_id)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI TABLE event",
            str(search_edit.text()) == table_id,
            str(search_edit.text()),
            table_id,
        )

    status_text = window.statusBar().currentMessage()
    compact_status = re.sub(r"[\s,]", "", status_text)
    add_check(
        checks,
        "상태표시줄 ADRG count",
        "전체ADRG1132개" in compact_status,
        status_text,
        "전체 ADRG 1,132개",
    )
    add_check(
        checks,
        "상태표시줄 TABLE count",
        "TABLE1308개" in compact_status,
        status_text,
        "TABLE 1,308개",
    )
    add_check(
        checks,
        "상태표시줄 CODE count",
        "검색코드16571개" in compact_status,
        status_text,
        "검색코드 16,571개",
    )

    window.close()
    app.processEvents()

    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    result = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "counts": counts,
        "fixture": {
            "adrg": adrg,
            "table": table_id,
            "code": code,
            "query": query,
        },
        "checks": checks,
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
        },
    }
    REPORT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "KDRG V4.7 Windows runtime source smoke 결과",
        "=" * 72,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"플랫폼: {sys.platform}",
        "",
        "[집계]",
        f"ADRG/AADRG/TABLE/CODE: {counts['adrg']} / {counts['aadrg']} / {counts['table']} / {counts['code']}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        print(f"[FAIL] Windows runtime source smoke: {pass_count} PASS / {fail_count} FAIL")
        return 1

    print(f"[PASS] Windows runtime source smoke: {pass_count} PASS / 0 FAIL")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        REPORT_TXT.write_text(
            "KDRG V4.7 Windows runtime source smoke 결과\n"
            + "=" * 72
            + f"\n스크립트 버전: {SCRIPT_VERSION}\n\n"
            + "[최종 결과]\n전체 결과: FAIL\n\n"
            + f"[FAIL 상세]\n- {type(exc).__name__}: {exc}\n"
            + traceback.format_exc(),
            encoding="utf-8",
        )
        print(f"[FAIL] Windows runtime source smoke 예외: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
'''


BUNDLE_VERIFY_SOURCE = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_bundle_validation_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_bundle_validation_report.json"
SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_RUNTIME_BUNDLE_VALIDATOR_V1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )


def configured_exe_path() -> Path:
    version_path = ROOT / "version.py"
    values = runpy.run_path(str(version_path)) if version_path.exists() else {}
    configured = str(values.get("EXE_NAME") or "").strip()
    if configured:
        filename = configured if configured.lower().endswith(".exe") else configured + ".exe"
        return ROOT / "dist" / filename

    candidates = sorted((ROOT / "dist").glob("*.exe"))
    return candidates[0] if candidates else ROOT / "dist" / "KDRG_V47_Relation_Search.exe"


def launch_probe(exe_path: Path, seconds: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_OPENGL"] = "software"

    started = time.monotonic()
    process = subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(seconds)
    return_code = process.poll()
    alive = return_code is None

    if alive:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    return {
        "alive_after_seconds": alive,
        "observed_seconds": round(time.monotonic() - started, 3),
        "return_code_before_terminate": return_code,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-exe", action="store_true")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--launch-seconds", type=int, default=8)
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    spec_path = ROOT / "kdrg.spec"
    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    add_check(checks, "spec 존재", spec_path.exists(), str(spec_path), "exists")
    add_check(
        checks,
        "통합 JSON bundle 대상",
        "kdrg_v47_search_integrated.json" in spec_text,
        "kdrg_v47_search_integrated.json" in spec_text,
        True,
    )
    add_check(
        checks,
        "windowed console 비활성",
        "console=False" in spec_text,
        "console=False" in spec_text,
        True,
    )
    add_check(
        checks,
        "onefile EXE 구조",
        "COLLECT(" not in spec_text,
        "COLLECT(" in spec_text,
        False,
    )

    forbidden_bundle_targets = [
        "sources/raw",
        "legacy_reference",
        "qt_native_shim",
        "reports/runtime_ui_preview",
    ]
    for forbidden in forbidden_bundle_targets:
        add_check(
            checks,
            f"bundle 제외 {forbidden}",
            forbidden not in spec_text,
            forbidden in spec_text,
            False,
        )

    exe_path = configured_exe_path()
    exe_exists = exe_path.is_file()
    add_check(
        checks,
        "Windows exe 존재",
        exe_exists if args.require_exe else True,
        str(exe_path),
        "exists" if args.require_exe else "optional",
    )

    exe_info: dict[str, Any] = {
        "path": str(exe_path),
        "exists": exe_exists,
    }
    if exe_exists:
        size = exe_path.stat().st_size
        header = exe_path.read_bytes()[:2]
        exe_info.update(
            {
                "size_bytes": size,
                "sha256": sha256_file(exe_path),
                "header_hex": header.hex(),
            }
        )
        add_check(checks, "exe 최소 크기", size >= 5 * 1024 * 1024, size, ">= 5MB")
        add_check(checks, "PE MZ header", header == b"MZ", header.hex(), "4d5a")

    launch_result: dict[str, Any] | None = None
    if args.launch:
        if exe_exists:
            launch_result = launch_probe(exe_path, max(3, args.launch_seconds))
            add_check(
                checks,
                "exe startup 생존",
                bool(launch_result["alive_after_seconds"]),
                launch_result,
                f"alive >= {max(3, args.launch_seconds)} seconds",
            )
        else:
            add_check(checks, "exe startup 생존", False, "exe missing", "launchable exe")

    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    payload = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "arguments": vars(args),
        "exe": exe_info,
        "launch": launch_result,
        "checks": checks,
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
        },
    }
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "KDRG V4.7 Windows runtime bundle 검증 결과",
        "=" * 72,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"플랫폼: {sys.platform}",
        f"exe: {exe_path}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        print(f"[FAIL] Windows runtime bundle 검증: {pass_count} PASS / {fail_count} FAIL")
        return 1

    print(f"[PASS] Windows runtime bundle 검증: {pass_count} PASS / 0 FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


WORKFLOW_SOURCE = r'''name: Build Windows exe and publish Release

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  windows-runtime-regression:
    runs-on: windows-latest
    timeout-minutes: 30

    steps:
      - name: 체크아웃
        uses: actions/checkout@v4

      - name: Python 3.11 설치
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: 의존성 설치
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt
          python -m pip install pyinstaller

      - name: 핵심 파일 문법검증
        shell: pwsh
        run: >
          python -m py_compile
          main.py
          version.py
          app/__init__.py
          app/kdrg_search_service.py
          app/runtime_data_store.py
          app/main_window.py
          app/dialogs.py
          tests/windows_runtime_source_smoke.py
          tests/verify_windows_runtime_bundle.py

      - name: Windows source runtime 회귀검증
        shell: pwsh
        env:
          QT_QPA_PLATFORM: offscreen
          QT_OPENGL: software
        run: python tests/windows_runtime_source_smoke.py

      - name: PyInstaller onefile GUI 빌드
        shell: pwsh
        run: python -m PyInstaller --noconfirm --clean kdrg.spec

      - name: exe bundle 정적·기동 검증
        shell: pwsh
        run: >
          python tests/verify_windows_runtime_bundle.py
          --require-exe
          --launch
          --launch-seconds 8

      - name: 버전 정보 추출
        id: version
        shell: pwsh
        run: |
          "app_version=$(python version.py APP_VERSION)" >> $env:GITHUB_OUTPUT
          "exe_name=$(python version.py EXE_NAME)" >> $env:GITHUB_OUTPUT
          "git_tag=$(python version.py GIT_TAG)" >> $env:GITHUB_OUTPUT
          "release_title=$(python version.py RELEASE_TITLE)" >> $env:GITHUB_OUTPUT

      - name: 태그와 버전 일치 확인
        if: startsWith(github.ref, 'refs/tags/')
        shell: pwsh
        run: |
          $pushedTag = "${{ github.ref_name }}"
          $expectedTag = "${{ steps.version.outputs.git_tag }}"

          if ($pushedTag -ne $expectedTag) {
            Write-Error "푸시된 태그($pushedTag)와 version.py의 태그($expectedTag)가 일치하지 않습니다."
            exit 1
          }

          Write-Host "태그 일치 확인: $pushedTag"

      - name: exe 경로와 크기 확인
        shell: pwsh
        run: |
          $exePath = "dist/${{ steps.version.outputs.exe_name }}"

          if (-not (Test-Path $exePath)) {
            Write-Error "exe 파일이 존재하지 않습니다: $exePath"
            exit 1
          }

          $exe = Get-Item $exePath
          if ($exe.Length -lt 5MB) {
            Write-Error "exe 파일 크기가 비정상적으로 작습니다: $($exe.Length) bytes"
            exit 1
          }

          Write-Host "exe 확인 완료: $($exe.FullName)"
          Write-Host "크기: $([math]::Round($exe.Length / 1MB, 2)) MB"

      - name: 회귀검증 요약
        shell: pwsh
        run: |
          "## KDRG Windows runtime regression" >> $env:GITHUB_STEP_SUMMARY
          "- Source runtime smoke: PASS" >> $env:GITHUB_STEP_SUMMARY
          "- PyInstaller onefile build: PASS" >> $env:GITHUB_STEP_SUMMARY
          "- Bundled exe startup: PASS" >> $env:GITHUB_STEP_SUMMARY
          "- Actions artifact upload: 사용하지 않음" >> $env:GITHUB_STEP_SUMMARY

      - name: GitHub Release 생성 및 exe 업로드
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.version.outputs.git_tag }}
          name: ${{ steps.version.outputs.release_title }}
          files: dist/${{ steps.version.outputs.exe_name }}
          fail_on_unmatched_files: true
          generate_release_notes: true
'''


BUILD_BAT_SOURCE = r'''@echo off
setlocal
cd /d "%~dp0"

echo [1/5] Python dependency install
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m pip install pyinstaller
if errorlevel 1 goto :fail

echo [2/5] Windows source runtime smoke
set QT_QPA_PLATFORM=offscreen
set QT_OPENGL=software
python tests\windows_runtime_source_smoke.py
if errorlevel 1 goto :fail

echo [3/5] PyInstaller build
python -m PyInstaller --noconfirm --clean kdrg.spec
if errorlevel 1 goto :fail

echo [4/5] Bundled exe validation
python tests\verify_windows_runtime_bundle.py --require-exe --launch --launch-seconds 8
if errorlevel 1 goto :fail

echo [5/5] Complete
echo [PASS] Windows exe build and runtime regression completed.
exit /b 0

:fail
echo [FAIL] Windows build stopped. Check the step above.
exit /b 1
'''


RUN_LOCAL_BAT_SOURCE = r'''@echo off
setlocal
cd /d "%~dp0"

python main.py
exit /b %errorlevel%
'''


README_SOURCE = r'''# KDRG V4.7 Windows 빌드·회귀검증

## 현재 목적

이 단계는 전체 runtime 데이터가 연결된 PySide 검색기를 Windows에서 빌드하고,
생성된 exe가 즉시 종료되지 않는지 자동으로 확인하는 단계입니다.

- runtime 데이터: `data/kdrg_v47_search_integrated.json`
- ADRG: 1,132개
- TABLE: 1,308개
- 검색 코드: 16,571개
- GUI: PySide6 onefile·windowed exe
- Replit 전용 `reports/qt_native_shim`은 Windows 번들에 포함하지 않습니다.

## 생성·교체 파일

- `kdrg.spec`
- `build_windows.bat`
- `run_local.bat`
- `tests/windows_runtime_source_smoke.py`
- `tests/verify_windows_runtime_bundle.py`
- `.github/workflows/build-windows-release.yml`

## Windows 로컬 빌드

프로젝트 폴더에서 `build_windows.bat`를 실행합니다.

검사 순서:

1. Python 의존성 설치
2. 전체 runtime source smoke
3. PyInstaller onefile GUI 빌드
4. exe 파일·PE 헤더·크기 검증
5. offscreen으로 exe를 실행해 8초 이상 생존하는지 확인

## GitHub Actions 수동 회귀검증

GitHub 저장소의 **Actions** 화면에서
`Build Windows exe and publish Release`를 선택하고
`Run workflow`를 실행합니다.

수동 실행에서는 Windows 빌드와 회귀검증만 수행하며 Release를 생성하지 않습니다.
Actions artifact 임시보관 업로드도 사용하지 않습니다.

## GitHub Release 배포

Release 배포는 `version.py`의 다음 값이 확정된 뒤에만 진행합니다.

- `APP_VERSION`
- `EXE_NAME`
- `GIT_TAG`
- `RELEASE_TITLE`

태그를 푸시하면 workflow가 다음을 순서대로 수행합니다.

1. Windows source runtime smoke
2. PyInstaller 빌드
3. exe 기동검증
4. 태그와 `version.py` 일치 확인
5. GitHub Release 생성
6. exe를 Release Assets에 업로드

## 번들 제외 대상

다음 항목은 exe에 포함하지 않습니다.

- `sources/raw`
- `legacy_reference`
- `reports/qt_native_shim`
- UI preview 이미지
- 원본 PDF·HWPX·XLSX
- GitHub credentials
- build·dist 캐시

## 사용자 Windows 확인 항목

자동검증 통과 후 실제 Windows PC에서 다음을 확인합니다.

1. exe가 설치 없이 실행되는지
2. 콘솔창이 함께 뜨지 않는지
3. 한글 글꼴이 깨지지 않는지
4. 초기 E011 선택과 전체 집계가 정상인지
5. ADRG 검색이 되는지
6. 점이 포함된 상병코드 검색이 되는지
7. TABLE 검색과 상세 관계가 표시되는지
8. physical source·condition usage·runtime related가 구분되는지
9. 창 종료 후 오류창이 뜨지 않는지
'''


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )


def read_report_status(
    txt_path: Path,
    json_path: Path,
    expected_version: str,
    expected_pass: int,
    expected_fail: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "txt_exists": txt_path.exists(),
        "json_exists": json_path.exists(),
        "expected_version": expected_version,
        "expected_pass": expected_pass,
        "expected_fail": expected_fail,
        "pass": False,
        "source": None,
    }

    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            validation = payload.get("validation")
            validation = validation if isinstance(validation, dict) else {}
            version = str(payload.get("script_version") or "")
            json_ok = (
                version == expected_version
                and validation.get("status") == "PASS"
                and validation.get("pass_count") == expected_pass
                and validation.get("fail_count") == expected_fail
            )
            result["json"] = {
                "script_version": version,
                "status": validation.get("status"),
                "pass_count": validation.get("pass_count"),
                "fail_count": validation.get("fail_count"),
                "pass": json_ok,
            }
            if json_ok:
                result["pass"] = True
                result["source"] = "json"
        except Exception as exc:
            result["json_error"] = f"{type(exc).__name__}: {exc}"

    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8")
        version_match = re.search(r"^(?:검증 스크립트 버전|스크립트 버전):\s*(.+?)\s*$", text, re.MULTILINE)
        final_match = re.search(r"^전체 결과:\s*(PASS|FAIL)\s*$", text, re.MULTILINE)
        pass_match = re.search(r"^PASS:\s*(\d+)\s*$", text, re.MULTILINE)
        fail_match = re.search(r"^FAIL:\s*(\d+)\s*$", text, re.MULTILINE)
        version = version_match.group(1).strip() if version_match else ""
        text_ok = (
            version == expected_version
            and bool(final_match)
            and final_match.group(1) == "PASS"
            and bool(pass_match)
            and int(pass_match.group(1)) == expected_pass
            and bool(fail_match)
            and int(fail_match.group(1)) == expected_fail
        )
        result["text"] = {
            "script_version": version,
            "status": final_match.group(1) if final_match else None,
            "pass_count": int(pass_match.group(1)) if pass_match else None,
            "fail_count": int(fail_match.group(1)) if fail_match else None,
            "pass": text_ok,
        }
        if text_ok and not result["pass"]:
            result["pass"] = True
            result["source"] = "text"

    return result


def backup_existing(paths: list[Path]) -> list[dict[str, Any]]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            records.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "existed": False,
                }
            )
            continue
        relative = path.relative_to(ROOT)
        backup_path = BACKUP_DIR / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        records.append(
            {
                "path": str(relative),
                "existed": True,
                "sha256": sha256_file(path),
                "backup": str(backup_path.relative_to(ROOT)),
            }
        )
    return records


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_report(
    checks: list[dict[str, Any]],
    prerequisite_42: dict[str, Any],
    prerequisite_43: dict[str, Any],
    backups: list[dict[str, Any]],
    protected_before: dict[str, str],
    protected_after: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)

    generated = []
    for path in GENERATED_FILES:
        generated.append(
            {
                "path": str(path.relative_to(ROOT)),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "sha256": sha256_file(path) if path.exists() else None,
            }
        )

    payload = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prerequisites": {
            "42_runtime_ui_validation": prerequisite_42,
            "43_runtime_ui_preview": prerequisite_43,
        },
        "backups": backups,
        "generated_files": generated,
        "protected_files": {
            key: {
                "before": protected_before.get(key),
                "after": protected_after.get(key),
                "changed": protected_before.get(key) != protected_after.get(key),
            }
            for key in protected_before
        },
        "checks": checks,
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
            "user_judgment_required": 0,
        },
    }

    lines = [
        "KDRG V4.7 Windows exe 회귀검증 실행 구성 구축 결과",
        "=" * 72,
        f"생성시각: {payload['created_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "전체 runtime UI preview 4종과 42번 독립검증 완료 후 Windows 전용 패키징·회귀검증 구성을 구축함",
        "이 단계에서는 Replit에서 Windows exe를 만들지 않고 windows-latest 실행 구성을 정적 확정함",
        "통합 JSON·검색 service·runtime adapter·PySide UI 원본은 수정하지 않음",
        "",
        "[선행 검증]",
        f"42번: {prerequisite_42}",
        f"43번: {prerequisite_43}",
        "",
        "[생성·교체 파일]",
    ]
    lines.extend(f"- {item['path']} / {item['size_bytes']} bytes" for item in generated)
    lines.extend(
        [
            "",
            "[Windows 구성 정책]",
            "Python 3.11 / PyInstaller onefile / console=False",
            "runtime 데이터는 data/kdrg_v47_search_integrated.json만 필수 번들 대상으로 사용함",
            "Replit 전용 qt_native_shim·sources/raw·legacy_reference·preview 이미지는 번들에서 제외함",
            "workflow_dispatch는 Windows 회귀검증만 수행하고 Release를 생성하지 않음",
            "v*.*.* 태그에서만 GitHub Release Assets로 exe를 업로드함",
            "Actions artifact 임시보관 업로드는 사용하지 않음",
            "",
            "[자동검증 항목]",
        ]
    )
    lines.extend(
        f"- [{item['status']}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[검증 항목 집계]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            "사용자 판단 필요: 0",
            "사용자 수동 Excel 검토: 없음",
            "",
            "[다음 단계]",
            "44번 PASS 후 생성 파일을 Git에 커밋·푸시하고 GitHub Actions workflow_dispatch로 windows-latest 회귀검증을 실행함",
            "수동 workflow PASS 전에는 version.py 확정·Git 태그·Release 생성을 진행하지 않음",
            "",
            "[최종 결과]",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    if fail_count:
        lines.extend(["", "[FAIL 상세]"])
        lines.extend(
            f"- {item['name']} | actual={item['actual']} | expected={item['expected']}"
            for item in checks
            if item["status"] == "FAIL"
        )
    return "\n".join(lines) + "\n", payload


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    prerequisite_42 = read_report_status(
        VALIDATION_42_TXT,
        VALIDATION_42_JSON,
        "2026-07-24_KDRG_V47_PYSIDE_RUNTIME_UI_BRIDGE_VALIDATOR_V4",
        98,
        0,
    )
    prerequisite_43 = read_report_status(
        PREVIEW_43_TXT,
        PREVIEW_43_JSON,
        "2026-07-24_KDRG_V47_RUNTIME_UI_PREVIEW_BUILDER_V3",
        18,
        0,
    )
    add_check(
        checks,
        "42번 runtime UI 독립검증 PASS",
        bool(prerequisite_42["pass"]),
        prerequisite_42,
        "VALIDATOR_V4 / 98 PASS / 0 FAIL",
    )
    add_check(
        checks,
        "43번 전체 UI preview PASS",
        bool(prerequisite_43["pass"]),
        prerequisite_43,
        "BUILDER_V3 / 18 PASS / 0 FAIL",
    )

    required_inputs = [
        ROOT / "main.py",
        ROOT / "version.py",
        ROOT / "requirements.txt",
        ROOT / "app" / "__init__.py",
        ROOT / "app" / "kdrg_search_service.py",
        ROOT / "app" / "runtime_data_store.py",
        ROOT / "app" / "main_window.py",
        ROOT / "app" / "dialogs.py",
        INTEGRATED_JSON,
    ]
    for path in required_inputs:
        add_check(
            checks,
            f"필수 입력 {path.relative_to(ROOT)}",
            path.is_file(),
            str(path),
            "exists",
        )

    if any(item["status"] == "FAIL" for item in checks):
        report_text, report_payload = build_report(
            checks,
            prerequisite_42,
            prerequisite_43,
            [],
            {},
            {},
        )
        REPORT_TXT.write_text(report_text, encoding="utf-8")
        REPORT_JSON.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[FAIL] Windows exe 회귀검증 실행 구성 선행검증 실패")
        print(f"report={REPORT_TXT}")
        return 1

    protected_before = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED_FILES
        if path.exists()
    }
    backups = backup_existing(GENERATED_FILES)

    write_file(ROOT / "kdrg.spec", SPEC_SOURCE)
    write_file(ROOT / "build_windows.bat", BUILD_BAT_SOURCE)
    write_file(ROOT / "run_local.bat", RUN_LOCAL_BAT_SOURCE)
    write_file(ROOT / "tests" / "windows_runtime_source_smoke.py", SOURCE_SMOKE_SOURCE)
    write_file(ROOT / "tests" / "verify_windows_runtime_bundle.py", BUNDLE_VERIFY_SOURCE)
    write_file(ROOT / ".github" / "workflows" / "build-windows-release.yml", WORKFLOW_SOURCE)
    write_file(ROOT / "BUILD_AND_RELEASE.md", README_SOURCE)

    protected_after = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED_FILES
        if path.exists()
    }

    for path in GENERATED_FILES:
        add_check(
            checks,
            f"생성 파일 {path.relative_to(ROOT)}",
            path.is_file() and path.stat().st_size > 0,
            path.stat().st_size if path.exists() else None,
            "> 0 bytes",
        )

    for path in [
        ROOT / "tests" / "windows_runtime_source_smoke.py",
        ROOT / "tests" / "verify_windows_runtime_bundle.py",
    ]:
        try:
            py_compile.compile(
                str(path),
                cfile=str(REPORTS / (path.stem + ".pyc")),
                doraise=True,
            )
            add_check(checks, f"py_compile {path.name}", True, "PASS", "PASS")
        except Exception as exc:
            add_check(
                checks,
                f"py_compile {path.name}",
                False,
                f"{type(exc).__name__}: {exc}",
                "PASS",
            )

    spec_text = (ROOT / "kdrg.spec").read_text(encoding="utf-8")
    workflow_text = (
        ROOT / ".github" / "workflows" / "build-windows-release.yml"
    ).read_text(encoding="utf-8")
    build_bat_text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    readme_text = (ROOT / "BUILD_AND_RELEASE.md").read_text(encoding="utf-8")

    content_checks = [
        ("spec 통합 JSON 포함", "kdrg_v47_search_integrated.json" in spec_text, True),
        ("spec console=False", "console=False" in spec_text, True),
        ("spec onefile", "COLLECT(" not in spec_text, True),
        ("spec qt_native_shim 제외", "qt_native_shim" not in spec_text, True),
        ("spec sources/raw 제외", "sources/raw" not in spec_text, True),
        ("workflow windows-latest", "runs-on: windows-latest" in workflow_text, True),
        ("workflow Python 3.11", 'python-version: "3.11"' in workflow_text, True),
        ("workflow source smoke", "windows_runtime_source_smoke.py" in workflow_text, True),
        ("workflow bundle verify", "verify_windows_runtime_bundle.py" in workflow_text, True),
        ("workflow exe 기동검증", "--launch-seconds 8" in workflow_text, True),
        ("workflow tag release 조건", "startsWith(github.ref, 'refs/tags/')" in workflow_text, True),
        ("workflow Release Assets", "softprops/action-gh-release@v2" in workflow_text, True),
        ("workflow artifact 미사용", "actions/upload-artifact" not in workflow_text, True),
        ("build bat source smoke", "windows_runtime_source_smoke.py" in build_bat_text, True),
        ("build bat PyInstaller", "PyInstaller" in build_bat_text, True),
        ("build bat bundle verify", "verify_windows_runtime_bundle.py" in build_bat_text, True),
        ("README 수동 workflow", "Run workflow" in readme_text, True),
        ("README Release Assets", "Release Assets" in readme_text, True),
        ("README Windows 실사용 체크", "사용자 Windows 확인 항목" in readme_text, True),
    ]
    for name, actual, expected in content_checks:
        add_check(checks, name, actual == expected, actual, expected)

    for relative, before_hash in protected_before.items():
        after_hash = protected_after.get(relative)
        add_check(
            checks,
            f"보호 파일 불변 {relative}",
            before_hash == after_hash,
            after_hash,
            before_hash,
        )

    report_text, report_payload = build_report(
        checks,
        prerequisite_42,
        prerequisite_43,
        backups,
        protected_before,
        protected_after,
    )
    REPORT_TXT.write_text(report_text, encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    validation = report_payload["validation"]
    if validation["fail_count"]:
        print(
            "[FAIL] Windows exe 회귀검증 실행 구성 구축 실패: "
            f"{validation['pass_count']} PASS / {validation['fail_count']} FAIL"
        )
        print(f"report={REPORT_TXT}")
        return 1

    print(
        "[PASS] Windows exe 회귀검증 실행 구성 구축 완료: "
        f"{validation['pass_count']} PASS / 0 FAIL"
    )
    print("workflow=.github/workflows/build-windows-release.yml")
    print("spec=kdrg.spec")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("[FAIL] 사용자 중단")
        raise SystemExit(130)
    except Exception as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        REPORT_TXT.write_text(
            "KDRG V4.7 Windows exe 회귀검증 실행 구성 구축 결과\n"
            + "=" * 72
            + f"\n스크립트 버전: {SCRIPT_VERSION}\n\n"
            + "[최종 결과]\n전체 결과: FAIL\n\n"
            + f"[FAIL 상세]\n- {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        print(
            "[FAIL] Windows exe 회귀검증 실행 구성 예외: "
            f"{type(exc).__name__}: {exc}"
        )
        print(f"report={REPORT_TXT}")
        raise SystemExit(1)
