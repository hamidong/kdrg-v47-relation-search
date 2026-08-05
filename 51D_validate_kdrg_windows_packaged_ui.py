#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026-08-04_KDRG_V47_STAGE51D_WINDOWS_PACKAGED_UI_VALIDATOR_V2"
EXPECTED_HEAD = "f2db7312174a4878d1829b7a753759162beebe52"
EXPECTED_DATA_SHA = "d865b8a421acb728b9cbc01ef3ba01036206bdc22b1877e70f938ead724e3dda"
EXPECTED_PACKAGE_VERSION = "0.5.1"
EXPECTED_ELECTRON = "43.2.0"
EXPECTED_BUILDER = "26.15.3"

ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_JSON = REPORT_DIR / "electron_stage51d_windows_packaged_ui_validation.json"
REPORT_TXT = REPORT_DIR / "electron_stage51d_windows_packaged_ui_validation.txt"

TARGET_FILES = (
    ".github/workflows/build-electron-windows.yml",
    "electron/main.js",
    "electron/src/packaged-runtime-smoke.js",
    "electron/scripts/verify-windows-portable.ps1",
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/README_STAGE51D_WINDOWS_UI.md",
)

checks: list[dict[str, Any]] = []
outputs: dict[str, Any] = {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_check(name: str, passed: bool, actual: Any, expected: Any) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "actual": actual,
            "expected": expected,
        }
    )


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"TimeoutExpired: {exc}",
        }
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def locate_node22() -> tuple[Path | None, Path | None]:
    candidates = [
        ROOT / "reports/electron_node_v22_cache/current/bin/node",
        Path(shutil.which("node") or ""),
    ]
    for node in candidates:
        if not node or not node.is_file():
            continue
        version = run([str(node), "--version"])
        if version["returncode"] != 0 or version["stdout"] != "v22.23.1":
            continue

        npm_candidates = [
            node.parent / "npm",
            node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js",
        ]
        for npm in npm_candidates:
            if npm.is_file():
                return node, npm
    return None, None


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    head_result = run(["git", "rev-parse", "HEAD"])
    head = head_result["stdout"]
    add_check("Git HEAD", head == EXPECTED_HEAD, head, EXPECTED_HEAD)

    for relative in TARGET_FILES:
        path = ROOT / relative
        add_check(f"파일 존재 {relative}", path.is_file(), path.is_file(), True)

    package_path = ELECTRON / "package.json"
    lock_path = ELECTRON / "package-lock.json"
    data_path = ROOT / "data/kdrg_v47_search_integrated_v3.json"

    package = json.loads(package_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    add_check(
        "package version 불변",
        package.get("version") == EXPECTED_PACKAGE_VERSION,
        package.get("version"),
        EXPECTED_PACKAGE_VERSION,
    )
    add_check(
        "Electron lock",
        lock.get("packages", {}).get("node_modules/electron", {}).get("version")
        == EXPECTED_ELECTRON,
        lock.get("packages", {}).get("node_modules/electron", {}).get("version"),
        EXPECTED_ELECTRON,
    )
    add_check(
        "electron-builder lock",
        lock.get("packages", {}).get("node_modules/electron-builder", {}).get("version")
        == EXPECTED_BUILDER,
        lock.get("packages", {}).get("node_modules/electron-builder", {}).get("version"),
        EXPECTED_BUILDER,
    )
    data_sha = sha256(data_path)
    add_check("운영 v3 SHA256", data_sha == EXPECTED_DATA_SHA, data_sha, EXPECTED_DATA_SHA)

    workflow = (ROOT / TARGET_FILES[0]).read_text(encoding="utf-8")
    main_source = (ROOT / TARGET_FILES[1]).read_text(encoding="utf-8")
    smoke_source = (ROOT / TARGET_FILES[2]).read_text(encoding="utf-8")
    ps_source = (ROOT / TARGET_FILES[3]).read_text(encoding="utf-8")
    test_source = (ROOT / TARGET_FILES[4]).read_text(encoding="utf-8")

    workflow_markers = (
        "KDRG_ELECTRON_UI_SMOKE_EVIDENCE.zip",
        "Packaged 실제 UI B013·B014·B018·B022·L033·9610: PASS",
        "Actions artifact upload: 사용하지 않음",
        "electron/dist/KDRG_ELECTRON_UI_SMOKE_EVIDENCE.zip",
    )
    for marker in workflow_markers:
        add_check(f"workflow marker {marker}", marker in workflow, marker in workflow, True)
    add_check(
        "workflow upload-artifact 미사용",
        "actions/upload-artifact" not in workflow,
        "actions/upload-artifact" in workflow,
        False,
    )

    smoke_branch = main_source.split("if (shouldRunPackagedSmoke())", 1)[-1].split(
        "registerIpcHandlers();\n    getSearchService();\n    mainWindow",
        1,
    )[0]
    add_check(
        "smoke branch IPC 등록",
        "registerIpcHandlers();" in smoke_branch,
        "registerIpcHandlers();" in smoke_branch,
        True,
    )
    add_check(
        "smoke branch service 준비",
        "getSearchService();" in smoke_branch,
        "getSearchService();" in smoke_branch,
        True,
    )

    smoke_markers = (
        "UI_SMOKE_SCHEMA_VERSION",
        "LT_B018_002",
        "LT_B018_003",
        "LT_B018_001",
        "LT_B018_004",
        "LT_B018_005",
        "분류 조건",
        "조건 상세",
        "원문 근거",
        "기본 분류 TABLE",
        "추가 분기조건",
        "capturePage",
        "inline-code-row",
        "console_error_count",
        "render_process_gone_count",
        "load_failure_count",
    )
    for marker in smoke_markers:
        add_check(f"smoke marker {marker}", marker in smoke_source, marker in smoke_source, True)

    legacy_smoke_contract_markers = (
        "obsolete items field detected",
        "legacy report no raw TypeError",
        "runPackagedRuntimeSmoke(fixture)",
        "runtime relation schema",
        "relation report failed step",
    )
    for marker in legacy_smoke_contract_markers:
        add_check(
            f"Stage 50D legacy smoke marker {marker}",
            marker in test_source,
            marker in test_source,
            True,
        )

    ps_markers = (
        "ScreenshotDirectory",
        "EvidenceZipPath",
        "UI screenshot distinct count",
        "renderer console error count",
        "B013",
        "B014",
        "B018",
        "B022",
        "L033",
        "9610",
        "Compress-Archive",
    )
    for marker in ps_markers:
        add_check(f"PowerShell marker {marker}", marker in ps_source, marker in ps_source, True)

    legacy_powershell_markers = (
        '$report.status -ne "PASS"',
        '$report.app_is_packaged -ne $true',
        '$report.counts.adrg -ne 1132',
    )
    for marker in legacy_powershell_markers:
        add_check(
            f"Stage 50D legacy PowerShell marker {marker}",
            marker in ps_source,
            marker in ps_source,
            True,
        )

    add_check(
        "smoke contract validator marker",
        "49 PASS / 0 FAIL" not in test_source,
        "고정 pass 수 문자열" in test_source,
        "동적 pass 수",
    )

    node, npm = locate_node22()
    add_check("Node 22.23.1", bool(node), str(node) if node else None, "available")
    add_check("npm CLI", bool(npm), str(npm) if npm else None, "available")

    if node:
        for relative in (
            "electron/main.js",
            "electron/src/packaged-runtime-smoke.js",
            "electron/tests/validate-packaged-runtime-smoke.js",
        ):
            result = run([str(node), "--check", str(ROOT / relative)])
            outputs[f"node --check {relative}"] = result
            add_check(
                f"node --check {relative}",
                result["returncode"] == 0,
                result,
                "returncode=0",
            )

        contract_result = run(
            [str(node), "tests/validate-packaged-runtime-smoke.js"],
            cwd=ELECTRON,
            timeout=120,
        )
        outputs["smoke contract"] = contract_result
        add_check(
            "packaged smoke contract",
            contract_result["returncode"] == 0
            and "Electron packaged runtime smoke 계약검증" in contract_result["stdout"]
            and "0 FAIL" in contract_result["stdout"],
            contract_result,
            "returncode=0 and 0 FAIL",
        )

    if node and npm:
        if npm.suffix == ".js":
            npm_command = [str(node), str(npm)]
        else:
            npm_command = [str(npm)]

        env = dict(os.environ)
        env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
        npm_result = run(
            [*npm_command, "run", "check"],
            cwd=ELECTRON,
            env=env,
            timeout=900,
        )
        outputs["npm run check"] = npm_result
        add_check(
            "전체 npm run check",
            npm_result["returncode"] == 0,
            npm_result,
            "returncode=0",
        )

    diff_check = run(["git", "diff", "--check"])
    outputs["git diff --check"] = diff_check
    add_check(
        "git diff --check",
        diff_check["returncode"] == 0 and not diff_check["stdout"] and not diff_check["stderr"],
        diff_check,
        "clean",
    )

    fail_count = sum(not item["passed"] for item in checks)
    pass_count = len(checks) - fail_count
    status = "PASS" if fail_count == 0 else "FAIL"

    payload = {
        "meta": {
            "schema_version": "kdrg-v47-stage51d-windows-packaged-ui-validation-v2",
            "validator": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        },
        "summary": {
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
        },
        "checks": checks,
        "outputs": outputs,
    }
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "KDRG V4.7 Stage 51D Windows packaged 실제 UI 독립검증",
        "=" * 78,
        f"validator={VERSION}",
        f"status={status}",
        f"PASS={pass_count}",
        f"FAIL={fail_count}",
        "",
    ]
    for item in checks:
        lines.append(
            f"- [{'PASS' if item['passed'] else 'FAIL'}] {item['name']} "
            f"| actual={item['actual']} | expected={item['expected']}"
        )
    lines.extend(["", "git_commit=아직 금지"])
    REPORT_TXT.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if fail_count:
        print(
            f"[FAIL] Stage 51D Windows packaged UI 독립검증: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print(f"report={REPORT_TXT}")
        return 1

    print(
        f"[PASS] Stage 51D Windows packaged UI 독립검증: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"report={REPORT_TXT}")
    print("git_commit=아직 금지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
