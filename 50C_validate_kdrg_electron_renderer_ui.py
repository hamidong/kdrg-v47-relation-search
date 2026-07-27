from __future__ import annotations

import hashlib
import json
import os
import platform
import py_compile
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_ELECTRON_STAGE50C_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
ELECTRON_ROOT = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50c_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50c_validation_report.json"

NODE_REQUIRED_MAJOR = 22
NODE_RELEASE_BASE = "https://nodejs.org/download/release/latest-v22.x"
NODE_CACHE_ROOT = ROOT.parent / ".cache" / "kdrg-stage50a-node-v22"

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "data/kdrg_v47_ui_semantic_profile.json": "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json": "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
    "app/kdrg_search_service.py": "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py": "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py": "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py": "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
    "version.py": "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c",
    "50A_validate_kdrg_electron_skeleton.py": "99b3ee00279ae7c9c7faf430656eebf594f33a817a2d79a135ec8d1db752de14",
    "electron/.gitignore": "aa5069a33ab1272d0dc50e9968d39d9ad10babc6c545cb10a3a84dd132882ab2",
    "electron/README_STAGE50A.md": "bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886",
    "electron/README_STAGE50B.md": "09dc1a57af65ee56121abc18158c4250cda6af258e7360596ce5f6c7cdfd320f",
    "electron/main.js": "a8b69820988321fdc2cd2f954b5c942434ecb663683a74cf5bd7e20c8804daf5",
    "electron/preload.js": "f20cc0a0694f2b365e9e5d67640ac8f3ecd23e86f15234e6614979bb9e4fb672",
    "electron/src/data-paths.js": "27cca98bdf68a2d5d71210c36bcddc6068e413000be860b4e9a1a784a4f61316",
    "electron/src/search-normalizer.js": "f59ccccd3a380df450d934b8bdd322f71c906fc68e69caa293e500d7f355d65e",
    "electron/src/search-result-contract.js": "cf979434aace8fde78c28130901295a2fb8e48049f5ef1ca4b69779cb5c48082",
    "electron/src/kdrg-search-service.js": "acecdeb55267341e7570e3f1c60a97f4f9abf9c74fb2c31ae2d64b84c48baad8",
    "electron/tests/run-search-parity.js": "9da5b1529c60f4ea3a7a0507e9a6a796cff3b60e52acd39aef3fd176c980b223",
}

TARGET_HASHES = {
    "50B_validate_kdrg_electron_search_service.py": "5ecea71469b3236557248faeab65dbb388342084280af6adeb351385188b06d3",
    "electron/package.json": "e61bf0fbf0a2520fdef5564ac2a17858627fd0711e17849f2f012d33a1d021a1",
    "electron/src/bootstrap-data.js": "311f077c22b1212ad0e428e83b31bf54b74247e0d121c28ec448a36affca2226",
    "electron/tests/validate-electron-skeleton.js": "be8d9163857c89d7a075063eef5e747685ebfd2f728c6d6b0bc7a02d0a58ff9a",
    "electron/tests/validate-search-service.js": "52a29ee49285bcb2ad9e9949f5bf65ec25cd44a56586ce1081fc383b6037e7f0",
    "electron/renderer/index.html": "d48516ee6a5b09db8c83d7155f5b2ee1c72a0919ca5a6ac6ed8ba149ad25552f",
    "electron/renderer/app.js": "43ea2db9431da87de40d72bd8eec373663f07fc8e986afecb212ee56e40790ce",
    "electron/renderer/styles.css": "275137e8f05bb78de982f0cf777db4e14b2a2aab702d6afb310062f79afe4c76",
    "electron/renderer/ui-formatters.js": "64f123958450a0f6081a1ecb0ac7b5b434f459e4e50b1685c5a35248b4630944",
    "electron/tests/validate-renderer-ui.js": "33a915a61cccdd0e4c716f4cd5f5b9c815bced6481dde7f4d8a37be2eeb6ae6f",
    "electron/README_STAGE50C.md": "35f92d8bd42649ee7bdb651979626235517ea06a3a185bae3128b2b212e0478f",
}

JS_CHECK_FILES = (
    "electron/src/bootstrap-data.js",
    "electron/tests/validate-electron-skeleton.js",
    "electron/tests/validate-search-service.js",
    "electron/renderer/ui-formatters.js",
    "electron/renderer/app.js",
    "electron/tests/validate-renderer-ui.js",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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
        return {"returncode": 127, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def parse_node_major(version_text: str) -> int:
    raw = version_text.strip().lstrip("v").split(".", 1)[0]
    try:
        return int(raw)
    except ValueError:
        return -1


def detect_node_arch() -> str:
    mapping = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    machine = platform.machine().lower()
    if machine not in mapping:
        raise RuntimeError(f"지원하지 않는 Linux architecture: {machine}")
    return mapping[machine]


def existing_node_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            NODE_CACHE_ROOT / "current/bin/node",
            Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),
            Path.home() / ".cache/kdrg-stage50a-node-v22/current/bin/node",
            Path.home() / ".nix-profile/bin/node",
            Path("/usr/local/bin/node"),
            Path("/usr/bin/node"),
        ]
    )
    for command in ("node", "nodejs"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    output: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def validate_node(path: Path) -> bool:
    result = run_command([str(path), "--version"], ROOT)
    return result["returncode"] == 0 and parse_node_major(result["stdout"]) >= NODE_REQUIRED_MAJOR


def safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination_resolved not in target.parents and target != destination_resolved:
            raise RuntimeError(f"tar 경로 이탈 감지: {member.name}")
        if member.issym() or member.islnk():
            link_target = (target.parent / member.linkname).resolve()
            if destination_resolved not in link_target.parents and link_target != destination_resolved:
                raise RuntimeError(f"tar 링크 경로 이탈 감지: {member.name}")
    archive.extractall(destination)


def download_portable_node() -> Path:
    arch = detect_node_arch()
    NODE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "KDRG-Stage50C-Validator/1.0"}
    shasums_url = f"{NODE_RELEASE_BASE}/SHASUMS256.txt"
    print("[INFO] Node.js v22 공식 SHA256 목록 확인 중...", flush=True)
    request = urllib.request.Request(shasums_url, headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        shasums_text = response.read().decode("utf-8")
    match = re.search(
        rf"^([0-9a-f]{{64}})  (node-v22\.[0-9.]+-linux-{re.escape(arch)}\.tar\.xz)$",
        shasums_text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"Node v22 Linux {arch} 배포파일을 찾지 못했습니다.")
    expected_sha, filename = match.groups()
    archive_path = NODE_CACHE_ROOT / filename
    partial_path = NODE_CACHE_ROOT / f"{filename}.partial"
    if not archive_path.exists() or sha256_file(archive_path) != expected_sha:
        archive_path.unlink(missing_ok=True)
        partial_path.unlink(missing_ok=True)
        print(f"[INFO] 공식 Node.js v22 portable 다운로드 시작: {filename}", flush=True)
        digest = hashlib.sha256()
        request = urllib.request.Request(f"{NODE_RELEASE_BASE}/{filename}", headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response, partial_path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != expected_sha:
            partial_path.unlink(missing_ok=True)
            raise RuntimeError("Node archive SHA256 불일치")
        partial_path.replace(archive_path)
    extract_root = NODE_CACHE_ROOT / "extracting"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with tarfile.open(archive_path, "r:xz") as archive:
        safe_extract_tar(archive, extract_root)
    extracted = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(extracted) != 1:
        raise RuntimeError(f"Node archive 최상위 디렉터리 수 오류: {len(extracted)}")
    current = NODE_CACHE_ROOT / "current"
    if current.exists() or current.is_symlink():
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        else:
            current.unlink()
    extracted[0].replace(current)
    shutil.rmtree(extract_root, ignore_errors=True)
    node_path = current / "bin/node"
    if not node_path.exists():
        raise RuntimeError(f"압축 해제 후 node 없음: {node_path}")
    return node_path


def locate_node() -> Path | None:
    for candidate in existing_node_candidates():
        if candidate.exists() and validate_node(candidate):
            os.environ["KDRG_NODE_BIN"] = str(candidate)
            os.environ["PATH"] = f"{candidate.parent}{os.pathsep}{os.environ.get('PATH', '')}"
            print(f"[INFO] Stage 50C Node 사용: {candidate}", flush=True)
            return candidate
    try:
        candidate = download_portable_node()
        if not validate_node(candidate):
            return None
        os.environ["KDRG_NODE_BIN"] = str(candidate)
        os.environ["PATH"] = f"{candidate.parent}{os.pathsep}{os.environ.get('PATH', '')}"
        print(f"[INFO] 공식 Node v22 portable runtime 준비 완료: {candidate}", flush=True)
        return candidate
    except Exception as exc:
        print(f"[FAIL] Node 준비 실패: {type(exc).__name__}: {exc}", flush=True)
        return None


def write_report(checks: list[dict[str, Any]], outputs: dict[str, dict[str, Any]]) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    failures = [item for item in checks if not item["passed"]]
    pass_count = len(checks) - len(failures)
    lines = [
        "KDRG V4.7 Stage 50C Electron renderer 검색 UI 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for item in checks:
        marker = "PASS" if item["passed"] else "FAIL"
        lines.append(f"- [{marker}] {item['name']} | actual={item['actual']} | expected={item['expected']}")
    for name, output in outputs.items():
        lines.extend(["", f"[{name} stdout]", output.get("stdout", ""), "", f"[{name} stderr]", output.get("stderr", "")])
    lines.extend(
        [
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
                "status": "PASS" if not failures else "FAIL",
                "pass": pass_count,
                "fail": len(failures),
                "total": len(checks),
                "checks": checks,
                "outputs": outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if failures:
        print(f"[FAIL] KDRG Stage 50C Electron renderer UI 검증: {pass_count} PASS / {len(failures)} FAIL")
        print("[FAIL 상세]")
        for item in failures:
            print(f"- {item['name']} | actual={item['actual']} | expected={item['expected']}")
        print(f"report={REPORT_TXT}")
        return 1
    print(f"[PASS] KDRG Stage 50C Electron renderer UI 검증: {pass_count} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0


def main() -> int:
    checks: list[dict[str, Any]] = []
    outputs: dict[str, dict[str, Any]] = {}

    def check(name: str, actual: Any, expected: Any, predicate=None) -> bool:
        passed = predicate(actual, expected) if predicate else actual == expected
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": bool(passed)})
        return bool(passed)

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative, expected_hash in TARGET_HASHES.items():
        path = ROOT / relative
        check(f"50C 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"50C 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    try:
        py_compile.compile(str(Path(__file__).resolve()), doraise=True)
        check("50C 독립검증기 py_compile", "PASS", "PASS")
    except Exception as exc:
        check("50C 독립검증기 py_compile", f"{type(exc).__name__}: {exc}", "PASS")

    package = json.loads((ELECTRON_ROOT / "package.json").read_text(encoding="utf-8"))
    check("package validate:ui", package.get("scripts", {}).get("validate:ui"), "node tests/validate-renderer-ui.js")
    check("package validate UI 연결", package.get("scripts", {}).get("validate", ""), "contains validate:ui", lambda value, _expected: "validate:ui" in value)
    check("Electron pin 유지", package.get("devDependencies", {}).get("electron"), "43.2.0")
    check("Node engine 유지", package.get("engines", {}).get("node"), ">=22.0.0")

    app_source = (ELECTRON_ROOT / "renderer/app.js").read_text(encoding="utf-8")
    html_source = (ELECTRON_ROOT / "renderer/index.html").read_text(encoding="utf-8")
    check("renderer require 미사용", "require(" in app_source, False)
    check("renderer innerHTML 미사용", "innerHTML" in app_source, False)
    check("renderer eval 미사용", bool(re.search(r"\beval\s*\(", app_source)), False)
    check("formatter 선로드", html_source.index("ui-formatters.js") < html_source.index("app.js"), True)
    check("기본 TABLE 문구", "기본 분류 TABLE" in app_source, True)
    check("추가조건 문구", "추가 분기조건" in app_source, True)
    check("제외 문구", "단, 다음 대상은 제외" in app_source, True)

    node = locate_node()
    check("Node v22 실행환경", str(node) if node else None, "available", lambda value, _expected: bool(value))
    if node:
        for relative in JS_CHECK_FILES:
            result = run_command([str(node), "--check", str(ROOT / relative)], ROOT)
            check(f"node --check {relative}", result["returncode"], 0)

        command_specs = {
            "50C renderer UI 검증": ([str(node), "tests/validate-renderer-ui.js"], ELECTRON_ROOT, "105 PASS / 0 FAIL"),
            "50B 검색 service 검증": ([str(node), "tests/validate-search-service.js"], ELECTRON_ROOT, "78 PASS / 0 FAIL"),
            "50C 보안 골격 검증": ([str(node), "tests/validate-electron-skeleton.js"], ELECTRON_ROOT, "PASS / 0 FAIL"),
            "50B Python 독립검증": ([sys.executable, "50B_validate_kdrg_electron_search_service.py"], ROOT, "66 PASS / 0 FAIL"),
        }
        for name, (args, cwd, marker) in command_specs.items():
            result = run_command(args, cwd)
            outputs[name] = result
            check(
                name,
                {"returncode": result["returncode"], "stdout": result["stdout"], "stderr": result["stderr"]},
                f"returncode=0 and {marker}",
                lambda value, expected_marker, marker=marker: value["returncode"] == 0 and marker in value["stdout"],
            )

    check("package-lock 미생성", (ELECTRON_ROOT / "package-lock.json").exists(), False)
    check("node_modules 미생성", (ELECTRON_ROOT / "node_modules").exists(), False)
    return write_report(checks, outputs)


if __name__ == "__main__":
    raise SystemExit(main())
