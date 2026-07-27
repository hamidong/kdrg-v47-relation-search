#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_ci_utf8_fix_validation_report.txt"
REPORT_JSON = REPORTS / "windows_ci_utf8_fix_validation_report.json"
SCRIPT_VERSION = "2026-07-27_KDRG_V47_WINDOWS_CI_UTF8_FIX_VALIDATOR_V1"

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "app/kdrg_search_service.py": "c9b09140ca0f2c0e498ccae3eb35e8b5f0f773d04cd93156faff21e6e5e79be4",
    "app/runtime_data_store.py": "dc42dcad29ebfaec6a0ad6359c5257d7849c268c9b6fb4982f29533ac13ef8ae",
    "app/main_window.py": "76ccc2578bae28b5cc5d21f18ae761cb605222d1bf50d381c35e202166acca17",
    "app/dialogs.py": "8303bbec03130e52e809dcf54ed7ae221a867857ac44342abd0be9f84d49d72c",
}

EXPECTED_REPLACEMENT_HASHES = {
    "tests/verify_windows_runtime_bundle.py": "b44b5e89b9dde1a5803f47c4f84d8dd389d8cabaef99c191c0b4cdd7c89e6edd",
    "tests/windows_runtime_source_smoke.py": "5b60835677bf7c641180ecec3f6bb5073ee74573215420ef1c8928f3ec7f8e87",
    ".github/workflows/build-windows-release.yml": "ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e",
}


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


def run_bytes(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def cp1252_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env["PYTHONIOENCODING"] = "cp1252"
    return env


def decoded_output(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stdout.decode("utf-8", errors="replace")


def build_temp_validator_project(temp_root: Path, spec_text: str) -> None:
    tests_dir = temp_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "tests" / "verify_windows_runtime_bundle.py",
        tests_dir / "verify_windows_runtime_bundle.py",
    )
    (temp_root / "version.py").write_text(
        'EXE_NAME = "KDRG_V47_Relation_Search_0.2.0.exe"\n',
        encoding="utf-8",
    )
    (temp_root / "kdrg.spec").write_text(spec_text, encoding="utf-8")


def validate_cp1252_paths(checks: list[dict[str, Any]]) -> None:
    env = cp1252_env()

    import_probe = (
        "import importlib.util, pathlib; "
        "p=pathlib.Path(r'" + str(ROOT / "tests" / "windows_runtime_source_smoke.py") + "'); "
        "s=importlib.util.spec_from_file_location('smoke_utf8_probe', p); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "m.print_failed_checks([{'status':'FAIL','name':'한글 검사','actual':'값','expected':'기대'}]); "
        "m.safe_print('[PASS] 한글 예외 출력')"
    )
    source_result = run_bytes([sys.executable, "-c", import_probe], ROOT, env)
    source_output = decoded_output(source_result)
    add_check(
        checks,
        "source smoke cp1252 실패상세 출력",
        source_result.returncode == 0
        and "UnicodeEncodeError" not in source_output
        and "[FAIL 상세]" in source_output
        and "한글 검사" in source_output,
        {"returncode": source_result.returncode, "output": source_output.strip()},
        "returncode=0 and UTF-8 Korean output",
    )

    pass_spec = "\n".join(
        [
            "datas = [('kdrg_v47_search_integrated.json', 'data')]",
            "console=False",
            "# onefile: COLLECT is intentionally absent",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="kdrg_utf8_pass_") as temp_dir:
        temp_root = Path(temp_dir)
        build_temp_validator_project(temp_root, pass_spec)
        result = run_bytes(
            [sys.executable, "tests/verify_windows_runtime_bundle.py"],
            temp_root,
            env,
        )
        output = decoded_output(result)
        add_check(
            checks,
            "bundle validator cp1252 PASS 경로",
            result.returncode == 0
            and "UnicodeEncodeError" not in output
            and "[PASS] Windows runtime bundle 검증" in output,
            {"returncode": result.returncode, "output": output.strip()},
            "returncode=0 and Korean PASS output",
        )

    fail_spec = "console=True\nCOLLECT('invalid')\nsources/raw\n"
    with tempfile.TemporaryDirectory(prefix="kdrg_utf8_fail_") as temp_dir:
        temp_root = Path(temp_dir)
        build_temp_validator_project(temp_root, fail_spec)
        result = run_bytes(
            [sys.executable, "tests/verify_windows_runtime_bundle.py"],
            temp_root,
            env,
        )
        output = decoded_output(result)
        add_check(
            checks,
            "bundle validator cp1252 FAIL 경로",
            result.returncode == 1
            and "UnicodeEncodeError" not in output
            and "[FAIL 상세]" in output
            and "통합 JSON bundle 대상" in output,
            {"returncode": result.returncode, "output": output.strip()},
            "returncode=1 with original FAIL details",
        )


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    required = [
        "tests/verify_windows_runtime_bundle.py",
        "tests/windows_runtime_source_smoke.py",
        ".github/workflows/build-windows-release.yml",
        "version.py",
        "kdrg.spec",
    ]
    for rel in required:
        path = ROOT / rel
        add_check(checks, f"필수 파일 {rel}", path.is_file(), str(path), "exists")

    if any(item["status"] == "FAIL" for item in checks):
        return write_reports(checks)

    for rel, expected_hash in EXPECTED_REPLACEMENT_HASHES.items():
        actual_hash = sha256_file(ROOT / rel)
        add_check(
            checks,
            f"전면교체본 SHA256 {rel}",
            actual_hash == expected_hash,
            actual_hash,
            expected_hash,
        )

    for rel in (
        "tests/verify_windows_runtime_bundle.py",
        "tests/windows_runtime_source_smoke.py",
    ):
        path = ROOT / rel
        try:
            py_compile.compile(str(path), doraise=True)
            actual = "PASS"
            passed = True
        except py_compile.PyCompileError as exc:
            actual = str(exc)
            passed = False
        add_check(checks, f"py_compile {rel}", passed, actual, "PASS")

    validator_text = (ROOT / "tests/verify_windows_runtime_bundle.py").read_text(encoding="utf-8")
    smoke_text = (ROOT / "tests/windows_runtime_source_smoke.py").read_text(encoding="utf-8")
    workflow_text = (ROOT / ".github/workflows/build-windows-release.yml").read_text(encoding="utf-8")

    for name, text in (
        ("bundle validator", validator_text),
        ("source smoke", smoke_text),
    ):
        ast.parse(text)
        add_check(
            checks,
            f"{name} UTF-8 stdio 일반화",
            "configure_utf8_stdio()" in text
            and 'encoding="utf-8"' in text
            and 'errors="backslashreplace"' in text,
            {
                "configure_utf8_stdio": "configure_utf8_stdio()" in text,
                "utf8": 'encoding="utf-8"' in text,
                "fallback": 'errors="backslashreplace"' in text,
            },
            "all True",
        )
        add_check(
            checks,
            f"{name} safe_print 적용",
            "def safe_print(" in text and "UnicodeEncodeError" in text,
            {
                "safe_print": "def safe_print(" in text,
                "UnicodeEncodeError": "UnicodeEncodeError" in text,
            },
            "all True",
        )

    workflow_rules = {
        "job PYTHONUTF8": 'PYTHONUTF8: "1"' in workflow_text,
        "job PYTHONIOENCODING": 'PYTHONIOENCODING: "utf-8"' in workflow_text,
        "source -X utf8": "python -X utf8 tests/windows_runtime_source_smoke.py" in workflow_text,
        "bundle -X utf8": "python -X utf8 tests/verify_windows_runtime_bundle.py" in workflow_text,
        "source report utf8": 'Get-Content "reports/windows_runtime_source_smoke_report.txt" -Encoding utf8' in workflow_text,
        "bundle report utf8": 'Get-Content "reports/windows_runtime_bundle_validation_report.txt" -Encoding utf8' in workflow_text,
        "artifact 미사용": "upload-artifact" not in workflow_text,
        "Release tag 전용": "if: startsWith(github.ref, 'refs/tags/')" in workflow_text,
    }
    for name, passed in workflow_rules.items():
        add_check(checks, f"workflow {name}", passed, passed, True)

    validate_cp1252_paths(checks)

    for rel, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / rel
        if not path.exists():
            add_check(checks, f"보호 파일 {rel}", False, "missing", expected_hash)
            continue
        actual_hash = sha256_file(path)
        add_check(
            checks,
            f"보호 파일 불변 {rel}",
            actual_hash == expected_hash,
            actual_hash,
            expected_hash,
        )

    return write_reports(checks)


def write_reports(checks: list[dict[str, Any]]) -> int:
    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    payload = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
        "KDRG V4.7 Windows CI UTF-8 일반화 수정 독립검증",
        "=" * 72,
        f"스크립트 버전: {SCRIPT_VERSION}",
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

    print(
        f"[{'PASS' if fail_count == 0 else 'FAIL'}] Windows CI UTF-8 fix: "
        f"{pass_count} PASS / {fail_count} FAIL"
    )
    print(f"report={REPORT_TXT}")
    if fail_count:
        print("[FAIL details]")
        for item in checks:
            if item["status"] == "FAIL":
                print(
                    f"- {item['name']} | actual={item['actual']} | expected={item['expected']}"
                )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
