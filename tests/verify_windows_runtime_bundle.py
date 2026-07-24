#!/usr/bin/env python3
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
