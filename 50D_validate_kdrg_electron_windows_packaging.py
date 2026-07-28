from __future__ import annotations

import hashlib
import json
import os
import py_compile
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
from urllib.parse import urlparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-28_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V6"
ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50d_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50d_validation_report.json"

PROTECTED_HASHES = {'data/kdrg_v47_search_integrated.json': '3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1', 'data/kdrg_v47_ui_semantic_profile.json': 'c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e', 'data/kdrg_v47_ui_display_contract.json': '9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac', 'app/kdrg_search_service.py': '35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd', 'app/runtime_data_store.py': 'e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d', 'app/main_window.py': '291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242', 'tests/windows_runtime_source_smoke.py': '5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907', 'version.py': '2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c', '.github/workflows/build-windows-release.yml': 'ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e', 'electron/preload.js': 'f20cc0a0694f2b365e9e5d67640ac8f3ecd23e86f15234e6614979bb9e4fb672', 'electron/src/data-paths.js': '27cca98bdf68a2d5d71210c36bcddc6068e413000be860b4e9a1a784a4f61316', 'electron/src/search-normalizer.js': 'f59ccccd3a380df450d934b8bdd322f71c906fc68e69caa293e500d7f355d65e', 'electron/src/search-result-contract.js': 'cf979434aace8fde78c28130901295a2fb8e48049f5ef1ca4b69779cb5c48082', 'electron/src/kdrg-search-service.js': 'acecdeb55267341e7570e3f1c60a97f4f9abf9c74fb2c31ae2d64b84c48baad8', 'electron/renderer/index.html': 'd48516ee6a5b09db8c83d7155f5b2ee1c72a0919ca5a6ac6ed8ba149ad25552f', 'electron/renderer/app.js': '43ea2db9431da87de40d72bd8eec373663f07fc8e986afecb212ee56e40790ce', 'electron/renderer/styles.css': '275137e8f05bb78de982f0cf777db4e14b2a2aab702d6afb310062f79afe4c76', 'electron/renderer/ui-formatters.js': '64f123958450a0f6081a1ecb0ac7b5b434f459e4e50b1685c5a35248b4630944', 'electron/tests/run-search-parity.js': '9da5b1529c60f4ea3a7a0507e9a6a796cff3b60e52acd39aef3fd176c980b223', 'electron/tests/validate-renderer-ui.js': '33a915a61cccdd0e4c716f4cd5f5b9c815bced6481dde7f4d8a37be2eeb6ae6f', 'electron/README_STAGE50A.md': 'bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886', 'electron/README_STAGE50B.md': '09dc1a57af65ee56121abc18158c4250cda6af258e7360596ce5f6c7cdfd320f', 'electron/README_STAGE50C.md': '35f92d8bd42649ee7bdb651979626235517ea06a3a185bae3128b2b212e0478f'}
TARGET_HASHES = {'50B_validate_kdrg_electron_search_service.py': '5b572166733af104a70d717f16bf777829b97229f735c3ef0b417d5bcd51c4ea', '50C_validate_kdrg_electron_renderer_ui.py': 'd40e700a607f43f64526f4b85ecd5b43c2c32d1f9511e2b813404f5297e8834f', 'electron/package.json': '37e6f5d39e88ea27a07d7712d71a307801245df0f6de3fd7d0cef5359ce1be6c', 'electron/main.js': '56d5dd8fce986e2883d58ab3f39aaba160dc05d98dc95a74409487fb0c61c208', 'electron/src/bootstrap-data.js': 'de31415aa829254a6e915f8f75cf845965073735712d74604502a9e431ff840c', 'electron/src/packaged-runtime-smoke.js': '4b9b26f56783008b2127e34ac2e653e70776a227501a8d1d4f5c1286d0e3ee30', 'electron/tests/validate-packaging-config.js': '34e59cd9cf7840f8e7be51633d6f237745f844a4753c54a8f60aaeccb96a56b2', 'electron/scripts/verify-windows-portable.ps1': '63c98bbd22a4358f0d9954e702686a03590180f03b254f1909508da9b8916500', '.github/workflows/build-electron-windows.yml': '21180545f7ab96056f6137d7bf55f9ccc71017b1842b8282a89e445b48c61f8b', 'electron/README_STAGE50D.md': 'adad88a75b3e2c3f20de83ffe3d5e086ca39cf8010d666a08527c18a7bb6cc26', 'electron/tests/validate-electron-skeleton.js': '223680c321fd582f5e4a1641236a673639e41aca3f2ca74ed80f46a0f6394fd0', 'electron/tests/validate-search-service.js': '60a55ea14bc2250d102bf952073736ff8208ee871a893996482d571f18df3d05', 'electron/scripts/validate-package-lock-registry.py': 'ef5dfd00fc5acdb68243119b0d40b71689103c52e02f4ad5c1db7dc66b995d92'}
EXPECTED_LOCK_HASH = "cf64b4826ff5feabb81b257797492528f4cbdc5c30d1a008d1960b2f1c003f8c"

JS_CHECK_FILES = (
    "electron/main.js",
    "electron/preload.js",
    "electron/src/data-paths.js",
    "electron/src/bootstrap-data.js",
    "electron/src/search-normalizer.js",
    "electron/src/search-result-contract.js",
    "electron/src/kdrg-search-service.js",
    "electron/src/packaged-runtime-smoke.js",
    "electron/renderer/ui-formatters.js",
    "electron/renderer/app.js",
    "electron/tests/validate-electron-skeleton.js",
    "electron/tests/validate-search-service.js",
    "electron/tests/run-search-parity.js",
    "electron/tests/validate-renderer-ui.js",
    "electron/tests/validate-packaging-config.js",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_resolved_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        resolved = value.get("resolved")
        if isinstance(resolved, str) and resolved.strip():
            urls.append(resolved.strip())
        for child in value.values():
            urls.extend(collect_resolved_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(collect_resolved_urls(child))
    return urls


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


NODE_REQUIRED_MAJOR = 22
NODE_RELEASE_BASE = "https://nodejs.org/download/release/latest-v22.x"
NODE_CACHE_ROOT = REPORT_DIR / "electron_node_v22_cache"


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
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    candidates.extend(
        [
            NODE_CACHE_ROOT / "current" / "bin" / "node",
            ROOT.parent / ".cache/kdrg-stage50a-node-v22/current/bin/node",
            Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),
            Path.home() / ".cache/kdrg-stage50a-node-v22/current/bin/node",
            Path.home() / ".nix-profile/bin/node",
            Path("/usr/local/bin/node"),
            Path("/usr/bin/node"),
        ]
    )

    for command in ("node", "nodejs"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve(strict=False))
        except OSError:
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

    headers = {"User-Agent": "KDRG-Stage50D-Validator/3.0"}
    shasums_url = f"{NODE_RELEASE_BASE}/SHASUMS256.txt"
    print("[INFO] Node.js v22 공식 SHA256 목록 확인 중...", flush=True)
    request = urllib.request.Request(shasums_url, headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
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

    archive_is_valid = False
    if archive_path.exists():
        cached_sha = sha256_file(archive_path)
        if cached_sha == expected_sha:
            archive_is_valid = True
            print(
                f"[INFO] SHA256가 확인된 기존 Node archive 재사용: {filename}",
                flush=True,
            )
        else:
            archive_path.unlink(missing_ok=True)

    if not archive_is_valid:
        partial_path.unlink(missing_ok=True)
        print(
            f"[INFO] 공식 Node.js v22 portable 다운로드 시작: {filename}",
            flush=True,
        )
        digest = hashlib.sha256()
        downloaded = 0
        request = urllib.request.Request(archive_url, headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response, partial_path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded % (5 * 1024 * 1024) < len(chunk):
                    print(
                        f"[INFO] Node archive 다운로드: {downloaded // (1024 * 1024)}MB",
                        flush=True,
                    )
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

    extracted_dirs = [path for path in extract_root.iterdir() if path.is_dir()]
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

    return node_path, {
        "source": "official_portable_download",
        "release_base": NODE_RELEASE_BASE,
        "architecture": arch,
        "archive": filename,
        "sha256": expected_sha,
        "cache_root": str(NODE_CACHE_ROOT),
    }


def activate_node(path: Path) -> None:
    os.environ["PATH"] = f"{path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ["KDRG_NODE_BIN"] = str(path)


def locate_node() -> Path | None:
    for candidate in existing_node_candidates():
        if not candidate.exists():
            continue
        result = validate_node_candidate(candidate)
        if result["usable"]:
            activate_node(candidate)
            print(
                f"[INFO] Stage 50D Node 사용: {candidate} ({result['version']})",
                flush=True,
            )
            return candidate

    try:
        node_path, _details = download_portable_node()
        validation = validate_node_candidate(node_path)
        if not validation["usable"]:
            raise RuntimeError(f"다운로드한 Node가 기준 미달: {validation}")
        activate_node(node_path)
        print(
            f"[INFO] 공식 Node v22 portable runtime 준비 완료: "
            f"{validation['version']} ({node_path})",
            flush=True,
        )
        return node_path
    except Exception as exc:
        print(
            f"[FAIL] Stage 50D용 Node v22 실행환경 준비 실패: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None


def write_report(
    checks: list[dict[str, Any]],
    outputs: dict[str, dict[str, Any]],
) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    failures = [item for item in checks if not item["passed"]]
    pass_count = len(checks) - len(failures)

    lines = [
        "KDRG V4.7 Stage 50D Electron Windows packaging 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for item in checks:
        marker = "PASS" if item["passed"] else "FAIL"
        lines.append(
            f"- [{marker}] {item['name']} | "
            f"actual={item['actual']} | expected={item['expected']}"
        )

    for name, result in outputs.items():
        lines.extend(
            [
                "",
                f"[{name} stdout]",
                result.get("stdout", ""),
                "",
                f"[{name} stderr]",
                result.get("stderr", ""),
            ]
        )

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
        print(
            f"[FAIL] KDRG Stage 50D Electron Windows packaging 검증: "
            f"{pass_count} PASS / {len(failures)} FAIL"
        )
        print("[FAIL 상세]")
        for item in failures:
            print(
                f"- {item['name']} | "
                f"actual={item['actual']} | expected={item['expected']}"
            )
        print(f"report={REPORT_TXT}")
        return 1

    print(
        f"[PASS] KDRG Stage 50D Electron Windows packaging 검증: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"report={REPORT_TXT}")
    return 0


def main() -> int:
    checks: list[dict[str, Any]] = []
    outputs: dict[str, dict[str, Any]] = {}

    def check(name: str, actual: Any, expected: Any, predicate=None) -> bool:
        passed = predicate(actual, expected) if predicate else actual == expected
        checks.append({
            "name": name,
            "actual": actual,
            "expected": expected,
            "passed": bool(passed),
        })
        return bool(passed)

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative, expected_hash in TARGET_HASHES.items():
        path = ROOT / relative
        check(f"50D 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"50D 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    lock_path = ELECTRON / "package-lock.json"
    check("package-lock 존재", lock_path.exists(), True)
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
        check("package-lock lockfileVersion", lock.get("lockfileVersion"), 3)
        check("package-lock root name", lock.get("name"), package.get("name"))
        check("package-lock root version", lock.get("version"), package.get("version"))
        check(
            "package-lock root Electron pin",
            lock.get("packages", {}).get("", {}).get("devDependencies", {}).get("electron"),
            "43.2.0",
        )
        check(
            "package-lock root electron-builder pin",
            lock.get("packages", {}).get("", {}).get("devDependencies", {}).get("electron-builder"),
            "26.15.3",
        )
        check(
            "package-lock resolved Electron",
            lock.get("packages", {}).get("node_modules/electron", {}).get("version"),
            "43.2.0",
        )
        check(
            "package-lock resolved electron-builder",
            lock.get("packages", {}).get("node_modules/electron-builder", {}).get("version"),
            "26.15.3",
        )
        check(
            "package-lock 실제 dependency graph",
            len(lock.get("packages", {})),
            ">= 50",
            lambda value, _expected: value >= 50,
        )
        check("package-lock SHA256 기록가능", len(sha256_file(lock_path)), 64)
        check("package-lock SHA256 고정", sha256_file(lock_path), EXPECTED_LOCK_HASH)
        resolved_urls = collect_resolved_urls(lock)
        internal_urls = [
            url for url in resolved_urls
            if "package-firewall.replit.local" in url.lower()
        ]
        plain_http_urls = [
            url for url in resolved_urls
            if url.lower().startswith("http://")
        ]
        official_urls = [
            url for url in resolved_urls
            if urlparse(url).hostname == "registry.npmjs.org"
        ]
        check(
            "package-lock resolved URL 수",
            len(resolved_urls),
            ">= 50",
            lambda value, _expected: value >= 50,
        )
        check("package-lock Replit 내부 registry URL 없음", len(internal_urls), 0)
        check("package-lock 평문 HTTP URL 없음", len(plain_http_urls), 0)
        check(
            "package-lock 공식 npm registry URL 전체",
            len(official_urls),
            len(resolved_urls),
        )

    for relative in (
        "50B_validate_kdrg_electron_search_service.py",
        "50C_validate_kdrg_electron_renderer_ui.py",
        "50D_validate_kdrg_electron_windows_packaging.py",
    ):
        try:
            py_compile.compile(str(ROOT / relative), doraise=True)
            check(f"py_compile {relative}", "PASS", "PASS")
        except Exception as exc:
            check(f"py_compile {relative}", f"{type(exc).__name__}: {exc}", "PASS")

    node = locate_node()
    check("Node v22 실행환경", str(node) if node else None, "available", lambda value, _expected: bool(value))
    if node:
        for relative in JS_CHECK_FILES:
            result = run_command([str(node), "--check", str(ROOT / relative)], ROOT)
            check(f"node --check {relative}", result["returncode"], 0)

        command_specs = {
            "Stage 50D packaging Node 검증": (
                [str(node), "tests/validate-packaging-config.js"],
                ELECTRON,
                "Electron Stage 50D Windows packaging 검증",
            ),
            "Stage 50C renderer UI 회귀검증": (
                [str(node), "tests/validate-renderer-ui.js"],
                ELECTRON,
                "105 PASS / 0 FAIL",
            ),
            "Stage 50C 검색 service 회귀검증": (
                [str(node), "tests/validate-search-service.js"],
                ELECTRON,
                "78 PASS / 0 FAIL",
            ),
            "Stage 50C 보안 골격 회귀검증": (
                [str(node), "tests/validate-electron-skeleton.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Stage 50C Python 전체 회귀검증": (
                [sys.executable, "50C_validate_kdrg_electron_renderer_ui.py"],
                ROOT,
                "85 PASS / 0 FAIL",
            ),
            "package-lock registry 독립검증": (
                [sys.executable, "scripts/validate-package-lock-registry.py"],
                ELECTRON,
                "package-lock registry canonicalization 검증",
            ),
        }
        for name, (args, cwd, marker) in command_specs.items():
            result = run_command(args, cwd)
            outputs[name] = result
            check(
                name,
                {
                    "returncode": result["returncode"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                },
                f"returncode=0 and {marker}",
                lambda value, _expected, marker=marker: (
                    value["returncode"] == 0 and marker in value["stdout"]
                ),
            )

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    check("Electron pin", package.get("devDependencies", {}).get("electron"), "43.2.0")
    check("electron-builder pin", package.get("devDependencies", {}).get("electron-builder"), "26.15.3")
    check("dist:win script", package.get("scripts", {}).get("dist:win"), "electron-builder --win portable --x64 --publish never")
    check("build portable target", package.get("build", {}).get("win", {}).get("target", [{}])[0].get("target"), "portable")
    check("build asar", package.get("build", {}).get("asar"), True)
    check("extraResources 수", len(package.get("build", {}).get("extraResources", [])), 3)

    workflow = (ROOT / ".github/workflows/build-electron-windows.yml").read_text(encoding="utf-8")
    check("Electron workflow manual 실행", "workflow_dispatch" in workflow, True)
    check("Electron workflow 태그 분리", 'electron-v*' in workflow, True)
    check("PySide 태그와 비충돌", '"v*.*.*"' in (ROOT / ".github/workflows/build-windows-release.yml").read_text(encoding="utf-8"), True)
    check("Actions checkout Node24 세대", "actions/checkout@v6" in workflow, True)
    check("Actions setup-node Node24 세대", "actions/setup-node@v6" in workflow, True)
    check("Actions setup-python Node24 세대", "actions/setup-python@v6" in workflow, True)
    check("npm CLI 11.17.0 고정", 'NPM_CLI_VERSION: "11.17.0"' in workflow, True)
    check(
        "공식 npm registry 고정",
        'NPM_CONFIG_REGISTRY: "https://registry.npmjs.org"' in workflow,
        True,
    )
    check(
        "package-lock registry 사전검증 단계",
        "package-lock 공식 registry 사전검증" in workflow,
        True,
    )
    check(
        "registry validator 실행",
        "scripts/validate-package-lock-registry.py" in workflow,
        True,
    )
    check(
        "npm ci 공식 registry 명시",
        "--registry=https://registry.npmjs.org" in workflow,
        True,
    )
    check("setup-node npm cache 미사용", "cache: npm" in workflow, False)
    job_env_start = workflow.find("    env:")
    steps_start = workflow.find("    steps:")
    job_env_block = (
        workflow[job_env_start:steps_start]
        if job_env_start >= 0 and steps_start > job_env_start
        else ""
    )
    check("workflow job env runner context 미사용", "${{ runner." in job_env_block, False)
    check("workflow 전체 runner context 조기평가 미사용", "${{ runner." in workflow, False)
    check("Actions 런타임 임시경로 초기화 단계", "Actions 런타임 임시경로 초기화" in workflow, True)
    check("RUNNER_TEMP 런타임 사용", "$env:RUNNER_TEMP" in workflow, True)
    check(
        "실행 식별자 환경변수 사용",
        "$env:GITHUB_RUN_ID" in workflow and "$env:GITHUB_RUN_ATTEMPT" in workflow,
        True,
    )
    check("실행별 fresh npm cache", "npm-cache-$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)" in workflow, True)
    check("npm cache GITHUB_ENV 전달", '"NPM_CONFIG_CACHE=$npmCache" >> $env:GITHUB_ENV' in workflow, True)
    check("Electron cache GITHUB_ENV 전달", '"ELECTRON_CACHE=$electronCache" >> $env:GITHUB_ENV' in workflow, True)
    check("builder cache GITHUB_ENV 전달", '"ELECTRON_BUILDER_CACHE=$builderCache" >> $env:GITHUB_ENV' in workflow, True)
    check("npm registry metadata 사용", "https://registry.npmjs.org/npm/$npmVersion" in workflow, True)
    check("npm tarball SHA512 검증", "SHA512" in workflow and "expectedIntegrity" in workflow, True)
    check("고정 npm CLI로 npm ci", "& node $npmCli ci" in workflow, True)
    check("npm ci 2회 복구", "$attempt -le 2" in workflow, True)
    check("npm debug log 출력", "*-debug-0.log" in workflow and "-Tail 250" in workflow, True)
    check("고정 npm CLI로 check", "& node $npmCli run check" in workflow, True)
    check("고정 npm CLI로 dist", "& node $npmCli run dist:win" in workflow, True)
    check("Actions artifact 미사용", "actions/upload-artifact" in workflow, False)
    check("Release Assets 사용", "softprops/action-gh-release@v2" in workflow, True)
    check("packaged smoke 사용", "verify-windows-portable.ps1" in workflow, True)

    check("node_modules 경로가 파일이 아님", (ELECTRON / "node_modules").is_file(), False)
    check("dist 경로가 파일이 아님", (ELECTRON / "dist").is_file(), False)

    return write_report(checks, outputs)


if __name__ == "__main__":
    raise SystemExit(main())
