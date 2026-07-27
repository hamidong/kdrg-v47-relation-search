#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 v0.2.1 버전 상승 독립검증."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import py_compile
import runpy
import subprocess
import sys
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_RELEASE_VERSION_V021_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"
TXT_REPORT = REPORT_DIR / "release_version_v021_validation_report.txt"
JSON_REPORT = REPORT_DIR / "release_version_v021_validation_report.json"

EXPECTED_VERSION = "0.2.1"
EXPECTED_VALUES = {
    "APP_VERSION": "0.2.1",
    "APP_NAME": "KDRG_V47_Relation_Search",
    "APP_DISPLAY_NAME": "KDRG V4.7 관계 검색기",
    "EXE_NAME": "KDRG_V47_Relation_Search_0.2.1.exe",
    "GIT_TAG": "v0.2.1",
    "RELEASE_TITLE": "KDRG V4.7 관계 검색기 v0.2.1",
}
EXPECTED_VERSION_SHA256 = "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c"
OLD_LITERALS = (
    "0.2.0",
    "v0.2.0",
    "KDRG_V47_Relation_Search_0.2.0.exe",
)

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "app/kdrg_search_service.py": "c9b09140ca0f2c0e498ccae3eb35e8b5f0f773d04cd93156faff21e6e5e79be4",
    "app/runtime_data_store.py": "dc42dcad29ebfaec6a0ad6359c5257d7849c268c9b6fb4982f29533ac13ef8ae",
    "app/main_window.py": "76ccc2578bae28b5cc5d21f18ae761cb605222d1bf50d381c35e202166acca17",
    "app/dialogs.py": "8303bbec03130e52e809dcf54ed7ae221a867857ac44342abd0be9f84d49d72c",
    "kdrg.spec": "762eacfbf30c4382ba967a1344c6d9e514bd3c34d840b9701f3155fe66785589",
    "main.py": "b0689ff655f465480f12e19e27fea5c2673be7def67a262ebaa7d923f8653b2c",
    "build_windows.bat": "f63bba20d2e8c67142758317d4f823c863065d3f248d429f51937e76b24ec742",
    "requirements.txt": "c151e1444f5e6b32649d21bf58ab678eb723e8289d552302f882909b6387f035",
    "tests/verify_windows_runtime_bundle.py": "b44b5e89b9dde1a5803f47c4f84d8dd389d8cabaef99c191c0b4cdd7c89e6edd",
    "tests/windows_runtime_source_smoke.py": "5b60835677bf7c641180ecec3f6bb5073ee74573215420ef1c8928f3ec7f8e87",
    ".github/workflows/build-windows-release.yml": "ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e",
    "45_validate_kdrg_windows_ci_utf8_output.py": "92b5f2b71e4a41e0a6c51632caeea514fbe98928ea063c90e1bc49789642274e",
}

RELEASE_CONTROL_FILES = (
    "version.py",
    "kdrg.spec",
    "main.py",
    "build_windows.bat",
    ".github/workflows/build-windows-release.yml",
    "tests/verify_windows_runtime_bundle.py",
    "tests/windows_runtime_source_smoke.py",
)


def configure_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(command: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def add(results: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any) -> None:
    results.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def main() -> int:
    configure_utf8_stdio()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    version_path = ROOT / "version.py"
    add(results, "version.py 존재", version_path.is_file(), str(version_path), "exists")

    if version_path.is_file():
        actual_hash = sha256(version_path)
        add(results, "version.py SHA256", actual_hash == EXPECTED_VERSION_SHA256, actual_hash, EXPECTED_VERSION_SHA256)

        try:
            py_compile.compile(str(version_path), doraise=True)
            add(results, "version.py py_compile", True, "PASS", "PASS")
        except Exception as exc:
            add(results, "version.py py_compile", False, f"{type(exc).__name__}: {exc}", "PASS")

        try:
            values = runpy.run_path(str(version_path))
            for key, expected in EXPECTED_VALUES.items():
                actual = values.get(key)
                add(results, f"version 값 {key}", actual == expected, actual, expected)
        except Exception as exc:
            add(results, "version.py 실행", False, f"{type(exc).__name__}: {exc}", "runpy PASS")

        try:
            tree = ast.parse(version_path.read_text(encoding="utf-8"))
            assignments = {
                node.targets[0].id: node.value
                for node in tree.body
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            }
            derived = {
                key: isinstance(assignments.get(key), ast.JoinedStr)
                for key in ("EXE_NAME", "GIT_TAG", "RELEASE_TITLE")
            }
            add(results, "파생 버전값 f-string 유지", all(derived.values()), derived, "all True")
        except Exception as exc:
            add(results, "파생 버전값 AST 검사", False, f"{type(exc).__name__}: {exc}", "PASS")

        for key, expected in EXPECTED_VALUES.items():
            command_result = run([sys.executable, "version.py", key])
            passed = command_result["returncode"] == 0 and command_result["stdout"] == expected
            add(results, f"CLI 출력 {key}", passed, command_result, expected)

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        add(results, f"보호 파일 불변 {relative}", actual == expected_hash, actual, expected_hash)

    stale_hits: list[dict[str, Any]] = []
    for relative in RELEASE_CONTROL_FILES:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for literal in OLD_LITERALS:
            if literal in text:
                stale_hits.append({"file": relative, "literal": literal})
    add(results, "배포 제어 파일 구버전 문자열 전수검사", not stale_hits, stale_hits, [])

    spec_text = (ROOT / "kdrg.spec").read_text(encoding="utf-8", errors="replace") if (ROOT / "kdrg.spec").is_file() else ""
    spec_rules = {
        "version.py 읽기": 'VERSION_FILE = ROOT / "version.py"' in spec_text,
        "EXE_NAME 사용": 'version_values.get("EXE_NAME")' in spec_text,
        "bundle_name 파생": "Path(configured_exe_name).stem" in spec_text,
    }
    add(results, "kdrg.spec 단일 버전축 연결", all(spec_rules.values()), spec_rules, "all True")

    workflow_path = ROOT / ".github/workflows/build-windows-release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace") if workflow_path.is_file() else ""
    workflow_rules = {
        "태그 트리거": '      - "v*.*.*"' in workflow_text,
        "version.py 출력 사용": "python version.py APP_VERSION" in workflow_text,
        "태그 일치 검증": "github.ref_name" in workflow_text and "steps.version.outputs.git_tag" in workflow_text,
        "Release Asset 동적 이름": "dist/${{ steps.version.outputs.exe_name }}" in workflow_text,
        "Actions artifact 미사용": "upload-artifact" not in workflow_text,
    }
    add(results, "workflow 버전·Release 연결", all(workflow_rules.values()), workflow_rules, "all True")

    local_tag = run(["git", "rev-parse", "-q", "--verify", "refs/tags/v0.2.1"])
    local_tag_absent = local_tag["returncode"] != 0
    add(results, "로컬 v0.2.1 태그 미생성", local_tag_absent, local_tag, "tag absent before release")

    pass_count = sum(1 for item in results if item["passed"])
    fail_items = [item for item in results if not item["passed"]]
    payload = {
        "script_version": SCRIPT_VERSION,
        "root": str(ROOT),
        "pass": pass_count,
        "fail": len(fail_items),
        "total": len(results),
        "results": results,
    }
    JSON_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "KDRG V4.7 v0.2.1 버전 상승 독립검증",
        "=" * 72,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for item in results:
        status = "PASS" if item["passed"] else "FAIL"
        lines.append(f"- [{status}] {item['name']} | actual={item['actual']} | expected={item['expected']}")
    lines.extend([
        "",
        "[최종 결과]",
        f"PASS: {pass_count}",
        f"FAIL: {len(fail_items)}",
        f"TOTAL: {len(results)}",
        f"전체 결과: {'PASS' if not fail_items else 'FAIL'}",
    ])
    TXT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_items:
        print(f"[FAIL] KDRG v0.2.1 버전 검증: {pass_count} PASS / {len(fail_items)} FAIL")
        print("[FAIL 상세]")
        for item in fail_items:
            print(f"- {item['name']} | actual={item['actual']} | expected={item['expected']}")
        print(f"report={TXT_REPORT}")
        return 1

    print(f"[PASS] KDRG v0.2.1 버전 검증: {pass_count} PASS / 0 FAIL")
    print(f"report={TXT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
