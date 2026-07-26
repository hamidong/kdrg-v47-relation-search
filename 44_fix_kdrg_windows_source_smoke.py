#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_SOURCE_SMOKE_FIX_BUILDER_V2"

ROOT = Path.cwd()
REPORTS = ROOT / "reports"
BACKUP_DIR = REPORTS / "windows_source_smoke_fix_backups"
REPORT_TXT = REPORTS / "windows_source_smoke_fix_report.txt"
REPORT_JSON = REPORTS / "windows_source_smoke_fix_report.json"

SMOKE_PATH = ROOT / "tests" / "windows_runtime_source_smoke.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "build-windows-release.yml"

PROTECTED_FILES = [
    ROOT / "data" / "kdrg_v47_search_integrated.json",
    ROOT / "app" / "kdrg_search_service.py",
    ROOT / "app" / "runtime_data_store.py",
    ROOT / "app" / "main_window.py",
    ROOT / "app" / "dialogs.py",
]


SMOKE_SOURCE = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("KDRG_DISABLE_SETTINGS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_source_smoke_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_source_smoke_report.json"
SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_RUNTIME_SOURCE_SMOKE_V2"


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


def normalize_text(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9가-힣]", "", str(value or "")).upper()


def result_keys(rows: Iterable[Any]) -> list[str]:
    return [str(getattr(row, "key", "")) for row in rows]


def has_result_key(rows: Iterable[Any], expected: str) -> bool:
    expected_norm = normalize_text(expected)
    return any(normalize_text(getattr(row, "key", "")) == expected_norm for row in rows)


def dotted_query(code: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    if len(normalized) > 3:
        return normalized[:3] + "." + normalized[3:]
    return normalized


def choose_searchable_fixture(
    store: Any,
    candidates: Iterable[str],
    category: str,
) -> tuple[str, list[Any]]:
    checked = 0
    for candidate in candidates:
        key = str(candidate or "").strip()
        if not key:
            continue
        checked += 1
        rows = store.search(key, category)
        if has_result_key(rows, key):
            return key, rows
        if checked >= 500:
            break
    return "", []


def choose_code_fixture(store: Any) -> tuple[str, str, list[Any]]:
    type_index = getattr(store, "_code_types_by_code", {})
    candidates = [
        str(code)
        for code in sorted(getattr(store, "code_to_tables", {}))
        if "상병코드" in set(type_index.get(code, set()))
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{3,}", str(code))
    ]
    for code in candidates[:1000]:
        query = dotted_query(code)
        rows = store.search(query, "상병코드")
        if has_result_key(rows, code):
            return code, query, rows
    return "", "", []


def print_failed_checks(checks: list[dict[str, Any]]) -> None:
    failed = [item for item in checks if item["status"] == "FAIL"]
    if not failed:
        return
    print("[FAIL 상세]")
    for item in failed:
        print(
            f"- {item['name']} | "
            f"actual={item['actual']} | expected={item['expected']}"
        )


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
    add_check(
        checks,
        "service status",
        isinstance(status, dict),
        type(status).__name__,
        "dict",
    )

    store = KDRGRuntimeDataStore()
    runtime_counts = dict(getattr(store, "runtime_counts", {}) or {})
    counts = {
        "adrg": len(getattr(store, "rules", {})),
        "aadrg": int(runtime_counts.get("aadrg_records", 0) or 0),
        "rdrg": int(runtime_counts.get("rdrg_records", 0) or 0),
        "table": len(getattr(store, "tables", {})),
        "code": len(getattr(store, "code_to_tables", {})),
    }

    add_check(checks, "ADRG count", counts["adrg"] == 1132, counts["adrg"], 1132)
    add_check(checks, "AADRG count", counts["aadrg"] == 1233, counts["aadrg"], 1233)
    add_check(checks, "RDRG count", counts["rdrg"] == 2699, counts["rdrg"], 2699)
    add_check(checks, "TABLE count", counts["table"] == 1308, counts["table"], 1308)
    add_check(checks, "CODE count", counts["code"] == 16571, counts["code"], 16571)

    adrg_candidates = [
        "E011",
        *sorted(str(key) for key in getattr(store, "rules", {})),
    ]
    adrg, adrg_rows = choose_searchable_fixture(store, adrg_candidates, "ADRG")
    add_check(
        checks,
        "ADRG searchable fixture",
        bool(adrg) and has_result_key(adrg_rows, adrg),
        {
            "fixture": adrg,
            "rows": result_keys(adrg_rows[:5]),
        },
        "current ADRG corpus에서 exact 검색 가능한 fixture",
    )

    table_candidates = [
        "LT_9610_001",
        *sorted(str(key) for key in getattr(store, "tables", {})),
    ]
    table_id, table_rows = choose_searchable_fixture(
        store,
        table_candidates,
        "TABLE",
    )
    add_check(
        checks,
        "TABLE searchable fixture",
        bool(table_id) and has_result_key(table_rows, table_id),
        {
            "fixture": table_id,
            "rows": result_keys(table_rows[:5]),
        },
        "current TABLE corpus에서 exact 검색 가능한 fixture",
    )

    code, query, code_rows = choose_code_fixture(store)
    add_check(
        checks,
        "점 표기 CODE searchable fixture",
        bool(code) and bool(query) and has_result_key(code_rows, code),
        {
            "fixture": code,
            "query": query,
            "rows": result_keys(code_rows[:5]),
        },
        "상병코드 corpus에서 점 표기 exact 검색 가능한 fixture",
    )

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()

    search_edit = getattr(window, "search_edit", None)
    category_combo = getattr(window, "category_combo", None)
    run_search = getattr(window, "run_search", None)

    add_check(
        checks,
        "MainWindow 생성",
        window is not None,
        type(window).__name__,
        "MainWindow",
    )
    add_check(
        checks,
        "검색창 계약",
        search_edit is not None,
        type(search_edit).__name__ if search_edit is not None else None,
        "QLineEdit",
    )
    add_check(
        checks,
        "검색유형 계약",
        category_combo is not None,
        type(category_combo).__name__ if category_combo is not None else None,
        "QComboBox",
    )
    add_check(
        checks,
        "검색 실행 계약",
        callable(run_search),
        callable(run_search),
        True,
    )

    initial_status = window.statusBar().currentMessage()
    compact_status = re.sub(r"[\s,]", "", initial_status)
    add_check(
        checks,
        "상태표시줄 ADRG count",
        "전체ADRG1132개" in compact_status,
        initial_status,
        "전체 ADRG 1,132개",
    )
    add_check(
        checks,
        "상태표시줄 AADRG count",
        "AADRG1233개" in compact_status,
        initial_status,
        "AADRG 1,233개",
    )
    add_check(
        checks,
        "상태표시줄 TABLE count",
        "TABLE1308개" in compact_status,
        initial_status,
        "TABLE 1,308개",
    )
    add_check(
        checks,
        "상태표시줄 CODE count",
        "검색코드16571개" in compact_status,
        initial_status,
        "검색코드 16,571개",
    )

    if (
        search_edit is not None
        and category_combo is not None
        and callable(run_search)
    ):
        category_combo.setCurrentText("ADRG")
        search_edit.setText(adrg)
        run_search()
        app.processEvents()
        ui_adrg_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI ADRG 결과",
            has_result_key(ui_adrg_rows, adrg),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_adrg_rows[:5]),
            },
            adrg,
        )

        category_combo.setCurrentText("상병코드")
        search_edit.setText(query)
        run_search()
        app.processEvents()
        ui_code_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI CODE 결과",
            has_result_key(ui_code_rows, code),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_code_rows[:5]),
            },
            code,
        )

        category_combo.setCurrentText("TABLE")
        search_edit.setText(table_id)
        run_search()
        app.processEvents()
        ui_table_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI TABLE 결과",
            has_result_key(ui_table_rows, table_id),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_table_rows[:5]),
            },
            table_id,
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
            "user_judgment_required": 0,
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
        (
            "ADRG/AADRG/RDRG/TABLE/CODE: "
            f"{counts['adrg']} / {counts['aadrg']} / {counts['rdrg']} / "
            f"{counts['table']} / {counts['code']}"
        ),
        "",
        "[동적 fixture]",
        f"ADRG: {adrg}",
        f"TABLE: {table_id}",
        f"CODE: {code} → {query}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | "
        f"actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            "사용자 판단 필요: 0",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        print(
            f"[FAIL] Windows runtime source smoke: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print_failed_checks(checks)
        print(f"report={REPORT_TXT}")
        return 1

    print(
        f"[PASS] Windows runtime source smoke: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"report={REPORT_TXT}")
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
        print(
            f"[FAIL] Windows runtime source smoke 예외: "
            f"{type(exc).__name__}: {exc}"
        )
        print(traceback.format_exc())
        print(f"report={REPORT_TXT}")
        raise SystemExit(1)
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
          KDRG_DISABLE_SETTINGS: "1"
        run: |
          python tests/windows_runtime_source_smoke.py
          $smokeExitCode = $LASTEXITCODE

          if (Test-Path "reports/windows_runtime_source_smoke_report.txt") {
            Write-Host ""
            Write-Host "===== windows_runtime_source_smoke_report.txt ====="
            Get-Content "reports/windows_runtime_source_smoke_report.txt"
          }

          exit $smokeExitCode

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


def backup(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT)
    if not path.exists():
        return {"path": str(relative), "existed": False}

    backup_path = BACKUP_DIR / relative
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return {
        "path": str(relative),
        "existed": True,
        "sha256": sha256_file(path),
        "backup": str(backup_path.relative_to(ROOT)),
    }


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    required = [
        ROOT / "data" / "kdrg_v47_search_integrated.json",
        ROOT / "app" / "kdrg_search_service.py",
        ROOT / "app" / "runtime_data_store.py",
        ROOT / "app" / "main_window.py",
        ROOT / "app" / "dialogs.py",
        ROOT / "tests" / "verify_windows_runtime_bundle.py",
        ROOT / "kdrg.spec",
    ]
    for path in required:
        add_check(
            checks,
            f"필수 입력 {path.relative_to(ROOT)}",
            path.is_file(),
            str(path),
            "exists",
        )

    if any(item["status"] == "FAIL" for item in checks):
        raise RuntimeError("필수 입력 파일이 누락됐습니다.")

    protected_before = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED_FILES
        if path.exists()
    }

    backups = [backup(SMOKE_PATH), backup(WORKFLOW_PATH)]
    write_file(SMOKE_PATH, SMOKE_SOURCE)
    write_file(WORKFLOW_PATH, WORKFLOW_SOURCE)

    py_compile.compile(
        str(SMOKE_PATH),
        cfile=str(REPORTS / "windows_runtime_source_smoke_V2.pyc"),
        doraise=True,
    )
    add_check(
        checks,
        "smoke V2 py_compile",
        True,
        "PASS",
        "PASS",
    )

    smoke_text = SMOKE_PATH.read_text(encoding="utf-8")
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    structural_checks = [
        (
            "AADRG count runtime_counts 사용",
            'runtime_counts.get("aadrg_records"' in smoke_text,
            True,
        ),
        (
            "존재하지 않는 aadrg_mapping 제거",
            'getattr(store, "aadrg_mapping"' not in smoke_text,
            True,
        ),
        (
            "검색 가능한 fixture 동적선정",
            "choose_searchable_fixture" in smoke_text,
            True,
        ),
        (
            "상병코드 유형 기반 fixture",
            "choose_code_fixture" in smoke_text,
            True,
        ),
        (
            "UI 결과 current_results 검증",
            'getattr(window, "current_results"' in smoke_text,
            True,
        ),
        (
            "초기 상태표시줄 검증",
            "initial_status = window.statusBar().currentMessage()" in smoke_text,
            True,
        ),
        (
            "FAIL 상세 stdout 출력",
            "print_failed_checks(checks)" in smoke_text,
            True,
        ),
        (
            "workflow smoke 보고서 출력",
            "Get-Content \"reports/windows_runtime_source_smoke_report.txt\"" in workflow_text,
            True,
        ),
        (
            "workflow smoke 종료코드 보존",
            "exit $smokeExitCode" in workflow_text,
            True,
        ),
        (
            "workflow Release tag 전용",
            "if: startsWith(github.ref, 'refs/tags/')" in workflow_text,
            True,
        ),
        (
            "workflow artifact 미사용",
            "actions/upload-artifact" not in workflow_text,
            True,
        ),
    ]
    for name, actual, expected in structural_checks:
        add_check(checks, name, actual == expected, actual, expected)

    protected_after = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED_FILES
        if path.exists()
    }
    for relative, before_hash in protected_before.items():
        after_hash = protected_after.get(relative)
        add_check(
            checks,
            f"보호 파일 불변 {relative}",
            before_hash == after_hash,
            after_hash,
            before_hash,
        )

    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    payload = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backups": backups,
        "generated": {
            str(SMOKE_PATH.relative_to(ROOT)): {
                "sha256": sha256_file(SMOKE_PATH),
                "size_bytes": SMOKE_PATH.stat().st_size,
            },
            str(WORKFLOW_PATH.relative_to(ROOT)): {
                "sha256": sha256_file(WORKFLOW_PATH),
                "size_bytes": WORKFLOW_PATH.stat().st_size,
            },
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
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "KDRG V4.7 Windows source smoke V2 보강 결과",
        "=" * 72,
        f"생성시각: {payload['created_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[원인]",
        "V1은 adapter에 존재하지 않는 aadrg_mapping 속성으로 AADRG 수를 계산하여 0건 오탐을 만들었음",
        "V1은 CI 실패 시 17 PASS / 2 FAIL 집계만 출력하고 실패 항목 상세를 runner log에 남기지 않았음",
        "",
        "[수정]",
        "AADRG/RDRG 수는 runtime service의 공식 runtime_counts에서 계산함",
        "ADRG·TABLE·상병코드 fixture는 현재 corpus에서 실제 exact 검색 가능한 값을 결정론적으로 선정함",
        "UI 검사는 입력창 문자열이 아니라 MainWindow.current_results의 실제 entity key를 검사함",
        "상태표시줄은 검색 이벤트 전 초기 전체 집계 상태에서 검사함",
        "실패 시 모든 FAIL 항목과 보고서 원문을 GitHub Actions log에 출력함",
        "",
        "[생성·교체 파일]",
        f"- {SMOKE_PATH.relative_to(ROOT)}",
        f"- {WORKFLOW_PATH.relative_to(ROOT)}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | "
        f"actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[검증 집계]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            "사용자 판단 필요: 0",
            "",
            "[최종 결과]",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        print(
            f"[FAIL] Windows source smoke V2 보강 실패: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print(f"report={REPORT_TXT}")
        return 1

    print(
        f"[PASS] Windows source smoke V2 보강 완료: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"smoke={SMOKE_PATH}")
    print(f"workflow={WORKFLOW_PATH}")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        REPORT_TXT.write_text(
            "KDRG V4.7 Windows source smoke V2 보강 결과\n"
            + "=" * 72
            + f"\n스크립트 버전: {SCRIPT_VERSION}\n\n"
            + "[최종 결과]\n전체 결과: FAIL\n\n"
            + f"[FAIL 상세]\n- {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        print(
            f"[FAIL] Windows source smoke V2 보강 예외: "
            f"{type(exc).__name__}: {exc}"
        )
        print(f"report={REPORT_TXT}")
        raise SystemExit(1)
