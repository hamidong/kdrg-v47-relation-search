# -*- coding: utf-8 -*-
"""KDRG V4.7 Stage 50A Electron 골격 독립검증."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_ELECTRON_STAGE50A_VALIDATOR_V4"
ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50a_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50a_validation_report.json"

EXPECTED_PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "data/kdrg_v47_ui_semantic_profile.json": "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json": "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
    "app/kdrg_search_service.py": "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py": "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py": "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py": "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
    "version.py": "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c",
}

EXPECTED_ELECTRON_HASHES = {
    "electron/.gitignore": "aa5069a33ab1272d0dc50e9968d39d9ad10babc6c545cb10a3a84dd132882ab2",
    "electron/README_STAGE50A.md": "bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886",
    "electron/main.js": "7f3a974ed4c299d5be2087390a6e7df7084ee81300f353de5e4284eed0a24070",
    "electron/package.json": "5cad1999326438f8123c8e4254e6733351aa3958f2abbfcdb34a83ecd498aff7",
    "electron/preload.js": "6851be864c7238211c4ce304851bea17042e923be98951739a247cee0c611538",
    "electron/renderer/app.js": "4fefe6b08ae5a6beb528b4b3b74dacea47e1ccbc2c180411059496fcc70abeed",
    "electron/renderer/index.html": "3c8531aa4f148315e880cbd5f6ba99f0eff8891226ae750d234ec9d0894b7637",
    "electron/renderer/styles.css": "1962c3a783fe5bc39178ebc65697c2fa9adcd8943e6abd6395423178f05215b5",
    "electron/src/bootstrap-data.js": "316402b545000093e2ef74e379170969bf85c260ec52ead86dd9c051f6c62f63",
    "electron/src/data-paths.js": "27cca98bdf68a2d5d71210c36bcddc6068e413000be860b4e9a1a784a4f61316",
    "electron/tests/validate-electron-skeleton.js": "a6088820868227eb04671d5cda4a11ebb2d0162a5cb072c698e0b2a6db763179",
}

JS_FILES = [
    "electron/main.js",
    "electron/preload.js",
    "electron/src/data-paths.js",
    "electron/src/bootstrap-data.js",
    "electron/renderer/app.js",
    "electron/tests/validate-electron-skeleton.js",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def write_node_preflight_report(message: str, details: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "KDRG V4.7 Stage 50A Electron 골격 독립검증 Node 사전점검",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[판정]",
        message,
        "",
        "[환경 상세]",
    ]
    for key, value in details.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "[기준]",
            "- Electron 최종 개발 목표는 package.json의 Node.js 22 이상 조건을 유지",
            "- Stage 50A의 JavaScript 문법·데이터 검증도 Node.js 22 이상으로 수행",
            "- PATH·명시 경로·로컬 cache만 빠르게 검사하고 없으면 공식 Node v22 portable 배포본을 SHA256 검증 후 사용",
            "",
            "전체 결과: FAIL",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "status": "FAIL",
                "stage": "node_preflight",
                "message": message,
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )



NODE_REQUIRED_MAJOR = 22
NODE_RELEASE_BASE = "https://nodejs.org/download/release/latest-v22.x"
NODE_CACHE_ROOT = Path.home() / ".cache" / "kdrg-stage50a-node-v22"


def parse_node_major(version_text: str) -> int:
    raw = version_text.strip().lstrip("v").split(".", 1)[0]
    try:
        return int(raw)
    except ValueError:
        return -1


def detect_node_arch() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    if machine not in mapping:
        raise RuntimeError(f"지원하지 않는 Linux architecture: {machine}")
    return mapping[machine]


def validate_node_candidate(path: Path) -> dict[str, Any]:
    result = run_command([str(path), "--version"], ROOT)
    major = parse_node_major(result["stdout"])
    return {
        "path": str(path),
        "returncode": result["returncode"],
        "version": result["stdout"],
        "stderr": result["stderr"],
        "major": major,
        "usable": result["returncode"] == 0 and major >= NODE_REQUIRED_MAJOR,
    }


def existing_node_candidates() -> list[Path]:
    """빠른 고정 경로만 검사한다.

    /nix/store 전체 glob은 Replit의 대규모 store에서 장시간 멈출 수 있으므로
    의도적으로 수행하지 않는다. PATH·명시 경로·로컬 cache 확인 후 바로
    공식 portable Node 설치 경로로 넘어간다.
    """
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    for command in ("node", "nodejs"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))

    candidates.extend(
        [
            NODE_CACHE_ROOT / "current" / "bin" / "node",
            Path.home() / ".nix-profile" / "bin" / "node",
            Path("/usr/local/bin/node"),
            Path("/usr/bin/node"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination_resolved not in target.parents and target != destination_resolved:
            raise RuntimeError(f"tar 경로 이탈 감지: {member.name}")
        if member.issym() or member.islnk():
            link_target = (target.parent / member.linkname).resolve()
            if (
                destination_resolved not in link_target.parents
                and link_target != destination_resolved
            ):
                raise RuntimeError(f"tar 링크 경로 이탈 감지: {member.name}")
    archive.extractall(destination)


def download_portable_node() -> tuple[Path, dict[str, Any]]:
    arch = detect_node_arch()
    NODE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    shasums_url = f"{NODE_RELEASE_BASE}/SHASUMS256.txt"
    request_headers = {"User-Agent": "KDRG-Stage50A-Builder/1.0"}
    print("[INFO] Node.js v22 공식 SHA256 목록 확인 중...", flush=True)
    shasums_request = urllib.request.Request(shasums_url, headers=request_headers)
    with urllib.request.urlopen(shasums_request, timeout=45) as response:
        shasums_text = response.read().decode("utf-8")

    pattern = re.compile(
        rf"^([0-9a-f]{{64}})  (node-v22\.[0-9.]+-linux-{re.escape(arch)}\.tar\.xz)$",
        re.MULTILINE,
    )
    match = pattern.search(shasums_text)
    if not match:
        raise RuntimeError(
            f"Node v22 Linux {arch} 배포파일을 SHASUMS256.txt에서 찾지 못했습니다."
        )

    expected_sha, filename = match.groups()
    archive_url = f"{NODE_RELEASE_BASE}/{filename}"
    archive_path = NODE_CACHE_ROOT / filename
    partial_path = NODE_CACHE_ROOT / f"{filename}.partial"

    digest = hashlib.sha256()
    if archive_path.exists():
        with archive_path.open("rb") as existing:
            while True:
                chunk = existing.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        cached_sha = digest.hexdigest()
        if cached_sha == expected_sha:
            actual_sha = cached_sha
            print(f"[INFO] SHA256가 확인된 기존 Node archive 재사용: {filename}", flush=True)
        else:
            archive_path.unlink()
            digest = hashlib.sha256()
            actual_sha = ""
    else:
        actual_sha = ""

    if not actual_sha:
        print(f"[INFO] 공식 Node.js v22 portable 다운로드 시작: {filename}", flush=True)
        archive_request = urllib.request.Request(archive_url, headers=request_headers)
        with urllib.request.urlopen(archive_request, timeout=120) as response, partial_path.open("wb") as out:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded % (5 * 1024 * 1024) < len(chunk):
                    print(f"[INFO] Node archive 다운로드: {downloaded // (1024 * 1024)}MB", flush=True)
        actual_sha = digest.hexdigest()
    if actual_sha != expected_sha:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Node archive SHA256 불일치: actual={actual_sha}, expected={expected_sha}"
        )
    partial_path.replace(archive_path)

    extract_root = NODE_CACHE_ROOT / "extracting"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)

    with tarfile.open(archive_path, "r:xz") as archive:
        safe_extract_tar(archive, extract_root)

    extracted_dirs = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(extracted_dirs) != 1:
        raise RuntimeError(
            f"Node archive 최상위 디렉터리 수가 예상과 다릅니다: {len(extracted_dirs)}"
        )

    current = NODE_CACHE_ROOT / "current"
    if current.exists() or current.is_symlink():
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        else:
            current.unlink()
    extracted_dirs[0].replace(current)
    shutil.rmtree(extract_root, ignore_errors=True)

    node_path = current / "bin" / "node"
    if not node_path.exists():
        raise RuntimeError(f"압축 해제 후 node 실행파일 없음: {node_path}")

    details = {
        "source": "official_portable_download",
        "release_base": NODE_RELEASE_BASE,
        "architecture": arch,
        "archive": filename,
        "sha256": actual_sha,
        "cache_root": str(NODE_CACHE_ROOT),
    }
    return node_path, details


def activate_node(path: Path) -> None:
    os.environ["PATH"] = f"{path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ["KDRG_NODE_BIN"] = str(path)


def ensure_node_runtime() -> int | None:
    attempts: list[dict[str, Any]] = []
    for candidate in existing_node_candidates():
        if not candidate.exists():
            continue
        result = validate_node_candidate(candidate)
        attempts.append(result)
        if result["usable"]:
            activate_node(candidate)
            print(f"[INFO] Stage 50A Node 사용: {candidate} ({result['version']})")
            return None

    try:
        node_path, download_details = download_portable_node()
        validation = validate_node_candidate(node_path)
        attempts.append(validation)
        if not validation["usable"]:
            raise RuntimeError(
                f"다운로드한 Node가 기준 미달: {validation}"
            )
        activate_node(node_path)
        print(
            f"[INFO] 공식 Node v22 portable runtime 준비 완료: "
            f"{validation['version']} ({node_path})"
        )
        return None
    except Exception as exc:
        write_node_preflight_report(
            "[FAIL] 기존 Node 탐색과 공식 Node v22 portable 설치가 모두 실패했습니다.",
            {
                "required_major": NODE_REQUIRED_MAJOR,
                "existing_attempts": attempts,
                "portable_error": f"{type(exc).__name__}: {exc}",
                "cache_root": str(NODE_CACHE_ROOT),
                "path": os.environ.get("PATH", ""),
            },
        )
        print("[FAIL] Stage 50A용 Node v22 실행환경 준비 실패")
        print(f"- {type(exc).__name__}: {exc}")
        print(f"report={REPORT_TXT}")
        return 1

def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.unlink(missing_ok=True)
    REPORT_JSON.unlink(missing_ok=True)
    REPORT_TXT.write_text(
        f"KDRG Stage 50A Node 사전점검 진행 중\n스크립트 버전: {SCRIPT_VERSION}\n",
        encoding="utf-8",
    )

    try:
        bootstrap_result = ensure_node_runtime()
    except KeyboardInterrupt:
        write_node_preflight_report(
            "[INTERRUPTED] Node 사전점검이 사용자 입력으로 중단됐습니다.",
            {
                "cache_root": str(NODE_CACHE_ROOT),
                "nix_store_full_scan": False,
                "next_action": "동일 V5 파일을 다시 실행",
            },
        )
        print("\n[INTERRUPTED] Stage 50A Node 사전점검 중단")
        print(f"report={REPORT_TXT}")
        return 130

    if bootstrap_result is not None:
        return bootstrap_result

    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any, passed: bool | None = None) -> None:
        ok = (actual == expected) if passed is None else bool(passed)
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": ok})

    for relative, expected in EXPECTED_PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"보호 파일 SHA256 {relative}", sha256(path), expected)

    for relative, expected in EXPECTED_ELECTRON_HASHES.items():
        path = ROOT / relative
        check(f"Electron 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"Electron 파일 SHA256 {relative}", sha256(path), expected)

    package_path = ROOT / "electron/package.json"
    package: dict[str, Any] = {}
    if package_path.exists():
        package = json.loads(package_path.read_text(encoding="utf-8"))
    check("package name", package.get("name"), "kdrg-v47-relation-search-electron")
    check("package version", package.get("version"), "0.3.0-dev.0")
    check("Electron 고정 버전", package.get("devDependencies", {}).get("electron"), "43.2.0")
    check("Node engine", package.get("engines", {}).get("node"), ">=22.0.0")
    check("package-lock 의도적 미생성", (ROOT / "electron/package-lock.json").exists(), False)
    check("node_modules 미생성", (ROOT / "electron/node_modules").exists(), False)

    for relative in JS_FILES:
        result = run_command(["node", "--check", str(ROOT / relative)], ROOT)
        check(f"node --check {relative}", result["returncode"], 0)

    node_result = run_command(
        ["node", "tests/validate-electron-skeleton.js"], ROOT / "electron"
    )
    check(
        "Node 독립검증 실행",
        node_result,
        "returncode=0 and PASS",
        node_result["returncode"] == 0
        and "[PASS] Electron Stage 50A Node 검증:" in node_result["stdout"],
    )
    check(
        "Node 검증 Unicode/예외 없음",
        node_result["stderr"],
        "",
        node_result["stderr"] == "",
    )

    main_source = (ROOT / "electron/main.js").read_text(encoding="utf-8")
    preload_source = (ROOT / "electron/preload.js").read_text(encoding="utf-8")
    renderer_source = (ROOT / "electron/renderer/app.js").read_text(encoding="utf-8")
    html_source = (ROOT / "electron/renderer/index.html").read_text(encoding="utf-8")

    source_rules = {
        "contextIsolation": "contextIsolation: true" in main_source,
        "nodeIntegration off": "nodeIntegration: false" in main_source,
        "sandbox": "sandbox: true" in main_source,
        "window open deny": "setWindowOpenHandler" in main_source and "action: 'deny'" in main_source,
        "navigation deny": "will-navigate" in main_source and "preventDefault" in main_source,
        "contextBridge": "contextBridge.exposeInMainWorld" in preload_source,
        "no direct ipc object": "exposeInMainWorld('KDRG', ipcRenderer" not in preload_source,
        "renderer no require": "require(" not in renderer_source,
        "renderer no innerHTML": "innerHTML" not in renderer_source,
        "CSP": "Content-Security-Policy" in html_source and "connect-src 'none'" in html_source,
    }
    for name, value in source_rules.items():
        check(f"보안 규칙 {name}", value, True)

    pass_count = sum(1 for item in checks if item["passed"])
    failures = [item for item in checks if not item["passed"]]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "KDRG V4.7 Stage 50A Electron 프로젝트 골격 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for item in checks:
        state = "PASS" if item["passed"] else "FAIL"
        lines.append(
            f"- [{state}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        )
    lines.extend(
        [
            "",
            "[Node 검증 stdout]",
            node_result["stdout"] or "(없음)",
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {len(failures)}",
            f"TOTAL: {len(checks)}",
            f"전체 결과: {'PASS' if not failures else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "checks": checks,
                "pass_count": pass_count,
                "fail_count": len(failures),
                "status": "PASS" if not failures else "FAIL",
                "node_result": node_result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if failures:
        print(
            f"[FAIL] KDRG Stage 50A Electron 골격 검증: {pass_count} PASS / {len(failures)} FAIL"
        )
        print("[FAIL 상세]")
        for item in failures:
            print(
                f"- {item['name']} | actual={item['actual']} | expected={item['expected']}"
            )
        print(f"report={REPORT_TXT}")
        return 1

    print(f"[PASS] KDRG Stage 50A Electron 골격 검증: {pass_count} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
