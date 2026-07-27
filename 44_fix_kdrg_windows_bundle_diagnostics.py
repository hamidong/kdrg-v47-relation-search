#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_WINDOWS_BUNDLE_DIAGNOSTICS_BUILDER_V1"

ROOT = Path.cwd()
REPORTS = ROOT / "reports"
BACKUP_DIR = REPORTS / "windows_bundle_diagnostics_backups"
REPORT_TXT = REPORTS / "windows_bundle_diagnostics_fix_report.txt"
REPORT_JSON = REPORTS / "windows_bundle_diagnostics_fix_report.json"

VALIDATOR = ROOT / "tests" / "verify_windows_runtime_bundle.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows-release.yml"

PROTECTED = [
    ROOT / "data" / "kdrg_v47_search_integrated.json",
    ROOT / "app" / "kdrg_search_service.py",
    ROOT / "app" / "runtime_data_store.py",
    ROOT / "app" / "main_window.py",
    ROOT / "app" / "dialogs.py",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT)
    if not path.exists():
        return {"path": str(relative), "existed": False}

    target = BACKUP_DIR / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return {
        "path": str(relative),
        "existed": True,
        "sha256": sha256_file(path),
        "backup": str(target.relative_to(ROOT)),
    }


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


def patch_validator(text: str) -> str:
    old_version = (
        'SCRIPT_VERSION = '
        '"2026-07-24_KDRG_V47_WINDOWS_RUNTIME_BUNDLE_VALIDATOR_V1"'
    )
    new_version = (
        'SCRIPT_VERSION = '
        '"2026-07-27_KDRG_V47_WINDOWS_RUNTIME_BUNDLE_VALIDATOR_V2"'
    )
    if old_version not in text:
        raise RuntimeError("bundle validator V1 버전 문자열을 찾지 못했습니다.")
    text = text.replace(old_version, new_version, 1)

    old_after_exe = '''    exe_info: dict[str, Any] = {
        "path": str(exe_path),
        "exists": exe_exists,
    }
'''
    new_after_exe = '''    dist_dir = ROOT / "dist"
    dist_candidates = [
        {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(dist_dir.glob("*"))
        if path.is_file()
    ]
    exe_info: dict[str, Any] = {
        "path": str(exe_path),
        "exists": exe_exists,
        "dist_candidates": dist_candidates,
    }
'''
    if old_after_exe not in text:
        raise RuntimeError("exe_info 생성 블록을 찾지 못했습니다.")
    text = text.replace(old_after_exe, new_after_exe, 1)

    old_final = '''    if fail_count:
        print(f"[FAIL] Windows runtime bundle 검증: {pass_count} PASS / {fail_count} FAIL")
        return 1

    print(f"[PASS] Windows runtime bundle 검증: {pass_count} PASS / 0 FAIL")
    return 0
'''
    new_final = '''    print(f"validator={SCRIPT_VERSION}")
    print(f"expected_exe={exe_path}")
    print(f"dist_candidates={dist_candidates}")
    print(f"launch_result={launch_result}")
    print(f"report={REPORT_TXT}")

    if fail_count:
        print(
            f"[FAIL] Windows runtime bundle 검증: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print("[FAIL 상세]")
        for item in checks:
            if item["status"] == "FAIL":
                print(
                    f"- {item['name']} | "
                    f"actual={item['actual']} | expected={item['expected']}"
                )
        return 1

    print(
        f"[PASS] Windows runtime bundle 검증: "
        f"{pass_count} PASS / 0 FAIL"
    )
    return 0
'''
    if old_final not in text:
        raise RuntimeError("bundle validator 최종 출력 블록을 찾지 못했습니다.")
    return text.replace(old_final, new_final, 1)


def patch_workflow(text: str) -> str:
    old_step = '''      - name: exe bundle 정적·기동 검증
        shell: pwsh
        run: >
          python tests/verify_windows_runtime_bundle.py
          --require-exe
          --launch
          --launch-seconds 8
'''
    new_step = '''      - name: exe bundle 정적·기동 검증
        shell: pwsh
        run: |
          Write-Host "===== dist directory ====="
          if (Test-Path "dist") {
            Get-ChildItem "dist" | Format-Table Name, Length, LastWriteTime
          } else {
            Write-Host "dist directory missing"
          }

          python tests/verify_windows_runtime_bundle.py `
            --require-exe `
            --launch `
            --launch-seconds 8
          $bundleExitCode = $LASTEXITCODE

          if (Test-Path "reports/windows_runtime_bundle_validation_report.txt") {
            Write-Host ""
            Write-Host "===== windows_runtime_bundle_validation_report.txt ====="
            Get-Content "reports/windows_runtime_bundle_validation_report.txt"
          } else {
            Write-Host "bundle validation report missing"
          }

          exit $bundleExitCode
'''
    if old_step not in text:
        raise RuntimeError("workflow bundle 검증 step을 찾지 못했습니다.")
    return text.replace(old_step, new_step, 1)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    for path in [VALIDATOR, WORKFLOW, *PROTECTED]:
        add_check(
            checks,
            f"필수 입력 {path.relative_to(ROOT)}",
            path.is_file(),
            str(path),
            "exists",
        )

    if any(item["status"] == "FAIL" for item in checks):
        raise RuntimeError("필수 입력 파일 누락")

    protected_before = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED
    }

    backups = [backup(VALIDATOR), backup(WORKFLOW)]

    validator_text = VALIDATOR.read_text(encoding="utf-8")
    workflow_text = WORKFLOW.read_text(encoding="utf-8")

    validator_text = patch_validator(validator_text)
    workflow_text = patch_workflow(workflow_text)

    VALIDATOR.write_text(validator_text, encoding="utf-8")
    WORKFLOW.write_text(workflow_text, encoding="utf-8")

    py_compile.compile(
        str(VALIDATOR),
        cfile=str(REPORTS / "verify_windows_runtime_bundle_V2.pyc"),
        doraise=True,
    )
    add_check(checks, "validator V2 py_compile", True, "PASS", "PASS")

    structural = [
        (
            "validator FAIL 상세 출력",
            'print("[FAIL 상세]")' in validator_text,
            True,
        ),
        (
            "validator dist 후보 출력",
            "dist_candidates=" in validator_text,
            True,
        ),
        (
            "validator launch 결과 출력",
            "launch_result=" in validator_text,
            True,
        ),
        (
            "workflow dist 목록 출력",
            'Get-ChildItem "dist"' in workflow_text,
            True,
        ),
        (
            "workflow bundle 보고서 출력",
            'Get-Content "reports/windows_runtime_bundle_validation_report.txt"'
            in workflow_text,
            True,
        ),
        (
            "workflow 종료코드 보존",
            "exit $bundleExitCode" in workflow_text,
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
    for name, actual, expected in structural:
        add_check(checks, name, actual == expected, actual, expected)

    protected_after = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in PROTECTED
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
            str(VALIDATOR.relative_to(ROOT)): {
                "sha256": sha256_file(VALIDATOR),
                "size_bytes": VALIDATOR.stat().st_size,
            },
            str(WORKFLOW.relative_to(ROOT)): {
                "sha256": sha256_file(WORKFLOW),
                "size_bytes": WORKFLOW.stat().st_size,
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
        "KDRG V4.7 Windows bundle 진단 V2 보강 결과",
        "=" * 72,
        f"생성시각: {payload['created_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 상황]",
        "Windows source smoke와 PyInstaller build는 PASS했고 bundle 정적·기동 검증에서 실패함",
        "기존 validator와 workflow는 실패 집계만 출력하여 정확한 FAIL 항목이 Actions log에 남지 않았음",
        "",
        "[보강]",
        "예상 exe 경로와 dist 전체 후보 파일을 출력함",
        "정적검증·크기·PE header·startup 생존 중 실패한 항목을 전부 출력함",
        "bundle 보고서 원문을 성공·실패와 관계없이 Actions log에 출력함",
        "기존 검증 기준은 완화하거나 우회하지 않음",
        "",
        "[교체 파일]",
        f"- {VALIDATOR.relative_to(ROOT)}",
        f"- {WORKFLOW.relative_to(ROOT)}",
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
            "[집계]",
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
            f"[FAIL] Windows bundle 진단 V2 보강 실패: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print(f"report={REPORT_TXT}")
        return 1

    print(
        f"[PASS] Windows bundle 진단 V2 보강 완료: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"validator={VALIDATOR}")
    print(f"workflow={WORKFLOW}")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        REPORT_TXT.write_text(
            "KDRG V4.7 Windows bundle 진단 V2 보강 결과\n"
            + "=" * 72
            + f"\n스크립트 버전: {SCRIPT_VERSION}\n\n"
            + "[최종 결과]\n전체 결과: FAIL\n\n"
            + f"[FAIL 상세]\n- {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        print(
            f"[FAIL] Windows bundle 진단 V2 보강 예외: "
            f"{type(exc).__name__}: {exc}"
        )
        print(f"report={REPORT_TXT}")
        raise SystemExit(1)
