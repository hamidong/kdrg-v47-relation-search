
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
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_VERSION = "2026-07-31_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V17_PUBLIC_ADRG_INLINE_TABLE_PREFLIGHT"
NODE_VERSION = "v22.23.1"

ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50d_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50d_validation_report.json"

NODE_CACHE_DIR = REPORT_DIR / "electron_node_v22_cache"
NODE_CURRENT_DIR = NODE_CACHE_DIR / "current"

EXPECTED_WORKFLOW_HASH = "fea2b590eede3403ba6c03a3627bb5e591ba7ab4226a4320d95dd3d8d29c002c"

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated_v3.json":
        "d865b8a421acb728b9cbc01ef3ba01036206bdc22b1877e70f938ead724e3dda",
    "data/kdrg_v47_ui_semantic_profile.json":
        "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json":
        "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
    "app/kdrg_search_service.py":
        "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py":
        "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py":
        "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py":
        "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
    "version.py":
        "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c",
    ".github/workflows/build-windows-release.yml":
        "ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e",
    ".gitattributes":
        "6e91da75eb4141a20f8296dce65a413d1a08befbebc6ebf9f485fa036fa73ff8",
    "electron/main.js":
        "3922ceb09ca64658941652008a6c1f8ff964fe25b9663ec594ca0b21325dd5d6",
    "electron/preload.js":
        "c42dbd945acc529b5235d1e5da834ebd9274eabd4e0d791b55d601e5962bb9a2",
    "electron/src/data-paths.js":
        "3d209ade16f25d9f2abfac5d43872b178276e74fba549388b220fa1f72a1dfa3",
    "electron/src/bootstrap-data.js":
        "45042a5e577e19a2083880ad6d56b465f1df324c63244ec25d57c58111f30cfe",
    "electron/src/search-normalizer.js":
        "f59ccccd3a380df450d934b8bdd322f71c906fc68e69caa293e500d7f355d65e",
    "electron/src/search-result-contract.js":
        "b941964ce4470dc71b4582c7b36f75bda73cb9ba308649ca626669bf36e82309",
    "electron/src/kdrg-search-service.js":
        "319ad5f29d5a2d8b3bd42d15dad074ab33cea1958452ed58e6138d4fda66a5ed",
    "electron/src/packaged-runtime-smoke.js":
        "8ff65a5e952f0beb6bbe14a07bbdaaefd8feccfe7ddf3eeb2aa5b604aa2ec9e4",
    "electron/renderer/ui-formatters.js":
        "e1c00fd9bcb33d577859ff948650c499a6b7504283b0aa75523f79eabaa1730a",
    "electron/tests/run-search-parity.js":
        "8b6c0dc6ef02477adc8bd1a5f7cbe62e651029e5ffbb295350f6f4eb2e9ad14a",
    "electron/tests/validate-electron-skeleton.js":
        "40d89f0323ded10bb32227c9ea2b059e96b618dec1ebc384c4712c1d92f7c948",
    "electron/tests/validate-search-service.js":
        "7a3308381b33836471fb1baebbe239443d1afe94854c159f4144ae0040f34642",
    "electron/tests/validate-packaging-config.js":
        "1a039921cc5342defa6856c2c17533e44ad6912b9e6620726dcdd47f219efad2",
    "electron/tests/validate-packaged-runtime-smoke.js":
        "28f366f1d2405c5e492ecd446a05c06b7bff414f2e3a5a42d218b238928f5569",
    "electron/tests/validate-release-version.js":
        "d4746b9ab38d914711ff5b6125a8ec33b9d46e574f94f9c1544f0a305bfd0471",
    "electron/scripts/verify-windows-portable.ps1":
        "fa8d5fa4a99b2624178df3b1e9942f7601c051b5143485a511f485d75e125ab9",
    "electron/scripts/validate-package-lock-registry.py":
        "ef5dfd00fc5acdb68243119b0d40b71689103c52e02f4ad5c1db7dc66b995d92",
    "electron/scripts/validate-checkout-byte-integrity.py":
        "19e05a48c2502b69a28ab5d4b277d33212b72c9c6df051b975441a47ef256876",
    "electron/README_STAGE50A.md":
        "bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886",
    "electron/README_STAGE50B.md":
        "09dc1a57af65ee56121abc18158c4250cda6af258e7360596ce5f6c7cdfd320f",
    "electron/README_STAGE50C.md":
        "35f92d8bd42649ee7bdb651979626235517ea06a3a185bae3128b2b212e0478f",
    "electron/README_STAGE50D.md":
        "adad88a75b3e2c3f20de83ffe3d5e086ca39cf8010d666a08527c18a7bb6cc26",
    "50B_validate_kdrg_electron_search_service.py":
        "851ec11913f142a7ccc354cd6b7c83d912dd0bf7a05da097f29e4d591d09fa1a",
    "50C_validate_kdrg_electron_renderer_ui.py":
        "e66136903a98099c5465babb255cbbff758bb4de2e6802a747a2007a22ef32a9",
}

MUTABLE_UI_FILES = (
    "electron/renderer/index.html",
    "electron/renderer/app.js",
    "electron/renderer/styles.css",
    "electron/tests/validate-renderer-ui.js",
)

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
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/tests/validate-packaging-config.js",
    "electron/tests/validate-release-version.js",
)

EXPECTED_STEPS = (
    "체크아웃",
    "Node.js 22.23.1 설치",
    "Python 3.11 설치",
    "checkout 바이트 무결성 검증",
    "Actions 런타임 임시경로 초기화",
    "package-lock 공식 registry 사전검증",
    "npm CLI 11.17.0 무결성 검증 준비",
    "npm 잠금 의존성 설치",
    "Electron source·검색·UI·packaging 검증",
    "Stage 50D Python 독립검증",
    "Windows x64 portable exe 빌드",
    "portable exe 경로 확인",
    "packaged exe 데이터·검색·renderer 기동검증",
    "SHA256 생성",
    "Electron 버전 정보 추출",
    "Electron 태그와 package 버전 일치 확인",
    "회귀검증 요약",
    "GitHub Release 생성 및 Electron exe 업로드",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], cwd: Path = ROOT) -> dict[str, Any]:
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


def node_version(node_path: Path) -> str | None:
    result = run_command([str(node_path), "--version"])
    if result["returncode"] != 0:
        return None
    return result["stdout"].strip()


def activate_node(node_path: Path) -> Path:
    os.environ["PATH"] = (
        f"{node_path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    )
    os.environ["KDRG_NODE_BIN"] = str(node_path)
    return node_path


def locate_node() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    exe_name = "node.exe" if os.name == "nt" else "node"
    candidates.extend(
        [
            NODE_CURRENT_DIR / "bin/node",
            NODE_CURRENT_DIR / "node.exe",
            ROOT.parent / ".cache/kdrg-stage50a-node-v22/current/bin/node",
        ]
    )

    resolved = shutil.which(exe_name) or shutil.which("node")
    if resolved:
        candidates.append(Path(resolved))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        if node_version(candidate) == NODE_VERSION:
            return activate_node(candidate)
    return None


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "KDRG-Stage50D-Validator/1.0"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with urllib.request.urlopen(request, timeout=120) as response:
        with temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
    temporary.replace(destination)


def expected_archive_hash(manifest_text: str, archive_name: str) -> str:
    for line in manifest_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == archive_name:
            digest = parts[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    raise RuntimeError(
        f"SHASUMS256.txt에서 {archive_name}의 SHA256을 찾지 못했습니다."
    )


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive_path, mode="r:xz") as archive:
        for member in archive.getmembers():
            member_target = (destination / member.name).resolve()
            try:
                member_target.relative_to(destination_resolved)
            except ValueError as exc:
                raise RuntimeError(
                    f"안전하지 않은 tar 경로가 발견됐습니다: {member.name}"
                ) from exc
        archive.extractall(destination)


def recover_node_v22() -> tuple[Path | None, str | None]:
    if os.name == "nt":
        return None, (
            "Windows에서는 actions/setup-node로 Node.js 22.23.1이 "
            "준비돼 있어야 합니다."
        )

    system_name = platform.system().lower()
    machine = platform.machine().lower()

    if system_name != "linux":
        return None, f"자동 복구 미지원 운영체제: {system_name}"

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    node_arch = arch_map.get(machine)
    if not node_arch:
        return None, f"자동 복구 미지원 CPU: {machine}"

    archive_name = f"node-{NODE_VERSION}-linux-{node_arch}.tar.xz"
    base_url = f"https://nodejs.org/dist/{NODE_VERSION}"
    manifest_path = NODE_CACHE_DIR / "SHASUMS256.txt"
    archive_path = NODE_CACHE_DIR / archive_name

    try:
        download_file(f"{base_url}/SHASUMS256.txt", manifest_path)
        manifest_text = manifest_path.read_text(encoding="utf-8")
        expected_hash = expected_archive_hash(manifest_text, archive_name)

        if (
            not archive_path.is_file()
            or sha256_file(archive_path) != expected_hash
        ):
            download_file(f"{base_url}/{archive_name}", archive_path)

        actual_hash = sha256_file(archive_path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Node.js archive SHA256 불일치: "
                f"actual={actual_hash}, expected={expected_hash}"
            )

        NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="node_extract_",
            dir=NODE_CACHE_DIR,
        ) as temporary_dir:
            extract_root = Path(temporary_dir)
            safe_extract_tar(archive_path, extract_root)
            extracted = (
                extract_root
                / f"node-{NODE_VERSION}-linux-{node_arch}"
            )
            node_path = extracted / "bin/node"
            if not node_path.is_file():
                raise RuntimeError(
                    f"압축 해제 후 Node 실행파일이 없습니다: {node_path}"
                )

            if NODE_CURRENT_DIR.exists():
                shutil.rmtree(NODE_CURRENT_DIR)
            shutil.move(str(extracted), str(NODE_CURRENT_DIR))

        final_node = NODE_CURRENT_DIR / "bin/node"
        final_node.chmod(final_node.stat().st_mode | 0o111)
        version = node_version(final_node)
        if version != NODE_VERSION:
            raise RuntimeError(
                f"복구된 Node 버전 불일치: {version} != {NODE_VERSION}"
            )
        return activate_node(final_node), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def ensure_node() -> tuple[Path | None, str, str | None]:
    located = locate_node()
    if located:
        return located, "reused", None

    recovered, error = recover_node_v22()
    if recovered:
        return recovered, "downloaded", None
    return None, "failed", error


def audit_workflow(text: str) -> list[tuple[str, Any, Any, bool]]:
    results: list[tuple[str, Any, Any, bool]] = []

    def add(name: str, actual: Any, expected: Any, passed: bool) -> None:
        results.append((name, actual, expected, passed))

    add("workflow 탭 문자 없음", "\t" in text, False, "\t" not in text)
    add(
        "workflow 최상위 step 이탈 없음",
        bool(re.search(r"(?m)^- name:", text)),
        False,
        re.search(r"(?m)^- name:", text) is None,
    )
    step_names = tuple(
        match.group(1).strip()
        for match in re.finditer(r"(?m)^      - name:\s*(.+)$", text)
    )
    add("workflow step 순서", step_names, EXPECTED_STEPS, step_names == EXPECTED_STEPS)
    add(
        "workflow 모든 named step 들여쓰기",
        len(re.findall(r"(?m)^\s*- name:", text)),
        len(EXPECTED_STEPS),
        len(re.findall(r"(?m)^      - name:", text)) == len(EXPECTED_STEPS)
        and len(re.findall(r"(?m)^\s*- name:", text)) == len(EXPECTED_STEPS),
    )

    trigger_block = '''"on":
  push:
    tags:
      - "electron-v*"
  workflow_dispatch: {}
'''
    add(
        "workflow trigger 계층",
        trigger_block in text,
        True,
        trigger_block in text,
    )
    add(
        "workflow 수동 실행 trigger 단일",
        text.count("workflow_dispatch:"),
        1,
        text.count("workflow_dispatch:") == 1,
    )
    add(
        "workflow jobs 계층",
        "jobs:\n  windows-electron-package:\n" in text,
        True,
        "jobs:\n  windows-electron-package:\n" in text,
    )
    add(
        "workflow steps 계층",
        "    steps:\n      - name: 체크아웃\n" in text,
        True,
        "    steps:\n      - name: 체크아웃\n" in text,
    )
    add(
        "checkout byte 검증 Python 이후",
        (
            set(("checkout 바이트 무결성 검증", "Python 3.11 설치"))
            <= set(step_names)
            and step_names.index("checkout 바이트 무결성 검증")
            > step_names.index("Python 3.11 설치")
        ),
        True,
        (
            set(("checkout 바이트 무결성 검증", "Python 3.11 설치"))
            <= set(step_names)
            and step_names.index("checkout 바이트 무결성 검증")
            > step_names.index("Python 3.11 설치")
        ),
    )
    checkout_hardening_tokens = (
        "git config --local core.autocrlf false",
        "git config --local core.eol lf",
        "git reset --hard HEAD",
        "git check-attr text eol -- .gitattributes",
        "git check-attr text eol -- electron/.gitignore",
        "git check-attr text eol -- electron/renderer/index.html",
        "git check-attr text eol -- electron/renderer/styles.css",
        "python -X utf8 electron/scripts/validate-checkout-byte-integrity.py",
    )
    add(
        "workflow checkout EOL 전수보강",
        all(token in text for token in checkout_hardening_tokens),
        True,
        all(token in text for token in checkout_hardening_tokens),
    )

    release_condition = (
        "if: github.event_name == 'push' "
        "&& startsWith(github.ref, 'refs/tags/electron-v')"
    )
    add(
        "태그 전용 조건 수",
        text.count(release_condition),
        2,
        text.count(release_condition) == 2,
    )
    add(
        "수동 실행 Release 차단",
        (
            release_condition in text
            and "GitHub Release 생성 및 Electron exe 업로드" in text
        ),
        True,
        (
            release_condition in text
            and "GitHub Release 생성 및 Electron exe 업로드" in text
        ),
    )
    add(
        "Actions artifact 미사용",
        "actions/upload-artifact" in text,
        False,
        "actions/upload-artifact" not in text,
    )
    add(
        "Release Assets 사용",
        "softprops/action-gh-release@v2" in text,
        True,
        "softprops/action-gh-release@v2" in text,
    )
    add(
        "workflow runner context 조기평가 없음",
        "${{ runner." in text,
        False,
        "${{ runner." not in text,
    )
    add(
        "workflow concurrency 존재",
        "concurrency:\n  group: kdrg-electron-windows-${{ github.ref }}"
        in text,
        True,
        "concurrency:\n  group: kdrg-electron-windows-${{ github.ref }}"
        in text,
    )
    return results


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
        ) + "\n",
        encoding="utf-8",
    )

    if failures:
        print(
            f"[FAIL] KDRG Stage 50D Electron Windows packaging 검증: "
            f"{pass_count} PASS / {len(failures)} FAIL"
        )
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
        checks.append(
            {
                "name": name,
                "actual": actual,
                "expected": expected,
                "passed": bool(passed),
            }
        )
        return bool(passed)

    workflow_path = ROOT / ".github/workflows/build-electron-windows.yml"
    check("Electron workflow 존재", workflow_path.is_file(), True)
    workflow_text = ""
    if workflow_path.is_file():
        workflow_text = workflow_path.read_text(encoding="utf-8")
        check(
            "Electron workflow SHA256",
            sha256_file(workflow_path),
            EXPECTED_WORKFLOW_HASH,
        )
        for name, actual, expected, passed in audit_workflow(workflow_text):
            checks.append(
                {
                    "name": name,
                    "actual": actual,
                    "expected": expected,
                    "passed": passed,
                }
            )

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.is_file(), True)
        if path.is_file():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative in MUTABLE_UI_FILES:
        path = ROOT / relative
        check(f"변경형 UI 파일 존재 {relative}", path.is_file(), True)
        if path.is_file():
            payload = path.read_bytes()
            check(f"변경형 UI LF 정책 {relative}", b"\r" not in payload, True)
            check(
                f"변경형 UI 단일 EOF LF {relative}",
                payload.endswith(b"\n") and not payload.endswith(b"\n\n"),
                True,
            )

    for relative in (
        "50B_validate_kdrg_electron_search_service.py",
        "50C_validate_kdrg_electron_renderer_ui.py",
        "50D_validate_kdrg_electron_windows_packaging.py",
        "electron/scripts/validate-package-lock-registry.py",
        "electron/scripts/validate-checkout-byte-integrity.py",
    ):
        try:
            py_compile.compile(str(ROOT / relative), doraise=True)
            check(f"py_compile {relative}", "PASS", "PASS")
        except Exception as exc:
            check(
                f"py_compile {relative}",
                f"{type(exc).__name__}: {exc}",
                "PASS",
            )

    attributes_text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    required_attributes = (
        "* text eol=lf",
        ".gitattributes text eol=lf",
        ".gitignore text eol=lf",
        "*.bat text eol=crlf",
        "*.cmd text eol=crlf",
    )
    check(
        ".gitattributes LF 정책",
        all(rule in attributes_text for rule in required_attributes),
        True,
    )

    critical_eol_files = (
        ".gitattributes",
        "electron/.gitignore",
        "electron/renderer/index.html",
        "electron/renderer/styles.css",
        "data/kdrg_v47_search_integrated_v3.json",
        "data/kdrg_v47_ui_semantic_profile.json",
        "data/kdrg_v47_ui_display_contract.json",
    )
    tracked_critical_result = run_command(
        [
            "git",
            "ls-files",
            "--",
            *critical_eol_files,
        ]
    )
    outputs["Git EOL 추적대상"] = tracked_critical_result
    check(
        "Git EOL 추적대상 조회 종료코드",
        tracked_critical_result["returncode"],
        0,
    )
    tracked_critical_files = [
        line.strip()
        for line in tracked_critical_result["stdout"].splitlines()
        if line.strip()
    ]

    eol_result = run_command(
        [
            "git",
            "ls-files",
            "--eol",
            "--",
            *tracked_critical_files,
        ]
    )
    outputs["Git EOL 정책"] = eol_result
    check("Git EOL 정책 종료코드", eol_result["returncode"], 0)

    eol_lines = [
        line
        for line in eol_result["stdout"].splitlines()
        if line.strip()
    ]
    eol_paths = {
        line.rsplit(None, 1)[-1]
        for line in eol_lines
    }
    untracked_critical_files = [
        relative
        for relative in critical_eol_files
        if relative not in tracked_critical_files
    ]
    untracked_eol_details = []
    for relative in untracked_critical_files:
        path = ROOT / relative
        attr_result = run_command(
            ["git", "check-attr", "eol", "--", relative]
        )
        outputs[f"Git EOL 속성 {relative}"] = attr_result
        raw = path.read_bytes() if path.is_file() else b""
        untracked_eol_details.append(
            {
                "file": relative,
                "exists": path.is_file(),
                "has_cr": b"\r" in raw,
                "attr_returncode": attr_result["returncode"],
                "attr_stdout": attr_result["stdout"].strip(),
                "ok": (
                    path.is_file()
                    and b"\r" not in raw
                    and attr_result["returncode"] == 0
                    and attr_result["stdout"].strip().endswith(": eol: lf")
                ),
            }
        )

    check(
        "Git EOL 핵심 텍스트 전체 LF",
        {
            "tracked_expected": sorted(tracked_critical_files),
            "tracked_reported": sorted(eol_paths),
            "tracked_lines": eol_lines,
            "untracked": untracked_eol_details,
        },
        "tracked=git ls-files --eol / untracked=byte+check-attr eol=lf",
        lambda value, _expected: (
            len(tracked_critical_files) + len(untracked_critical_files)
            == len(critical_eol_files)
            and value["tracked_reported"] == value["tracked_expected"]
            and len(value["tracked_lines"]) == len(tracked_critical_files)
            and all(
                "i/lf" in line and "attr/text eol=lf" in line
                for line in value["tracked_lines"]
            )
            and all(item["ok"] for item in value["untracked"])
        ),
    )

    lock_path = ELECTRON / "package-lock.json"
    check("package-lock 존재", lock_path.is_file(), True)
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
        version_text = str(package.get("version", ""))
        check("package version semver", bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version_text)), True)
        check("package name", package.get("name"), "kdrg-v47-relation-search-electron")
        check("package-lock lockfileVersion", lock.get("lockfileVersion"), 3)
        check("package-lock root name", lock.get("name"), package.get("name"))
        check("package-lock top version", lock.get("version"), package.get("version"))
        check("package-lock root version", lock.get("packages", {}).get("", {}).get("version"), package.get("version"))
        check(
            "Electron pin",
            package.get("devDependencies", {}).get("electron"),
            "43.2.0",
        )
        check(
            "electron-builder pin",
            package.get("devDependencies", {}).get("electron-builder"),
            "26.15.3",
        )
        urls = collect_resolved_urls(lock)
        official = [
            url for url in urls
            if urlparse(url).hostname == "registry.npmjs.org"
        ]
        internal = [
            url for url in urls
            if "package-firewall.replit.local" in url.lower()
        ]
        plain_http = [
            url for url in urls
            if url.lower().startswith("http://")
        ]
        check(
            "package-lock resolved URL 수",
            len(urls),
            ">= 50",
            lambda value, _expected: value >= 50,
        )
        check("package-lock 공식 registry 전체", len(official), len(urls))
        check("package-lock 내부 registry 없음", len(internal), 0)
        check("package-lock 평문 HTTP 없음", len(plain_http), 0)

    node, node_state, node_error = ensure_node()
    outputs["Node.js 22 준비"] = {
        "returncode": 0 if node else 1,
        "stdout": (
            f"state={node_state}\n"
            f"path={node if node else ''}\n"
            f"version={node_version(node) if node else ''}"
        ),
        "stderr": node_error or "",
    }
    check(
        "Node.js 22 실행환경",
        str(node) if node else node_error,
        "available",
        lambda value, _expected: bool(node),
    )
    check(
        "Node.js 22 준비 방식",
        node_state,
        "reused or downloaded",
        lambda value, _expected: value in {"reused", "downloaded"},
    )
    if node:
        version_result = run_command([str(node), "--version"])
        outputs["Node version"] = version_result
        check("Node.js 버전", version_result["stdout"], "v22.23.1")

        for relative in JS_CHECK_FILES:
            result = run_command([str(node), "--check", str(ROOT / relative)])
            check(f"node --check {relative}", result["returncode"], 0)

        command_specs = {
            "Stage 50B parity status 계약 self-test": (
                [str(node), "tests/run-search-parity.js", "--self-test"],
                ELECTRON,
                "Python-JavaScript recursive subset parity self-test: 10 PASS / 0 FAIL",
            ),
            "Stage 50D packaged smoke 계약 회귀검증": (
                [str(node), "tests/validate-packaged-runtime-smoke.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Electron release version 일관성 검증": (
                [str(node), "tests/validate-release-version.js", str(json.loads((ELECTRON / "package.json").read_text(encoding="utf-8")).get("version", ""))],
                ELECTRON,
                "Electron release version 검증",
            ),
            "Stage 50D packaging Node 검증": (
                [str(node), "tests/validate-packaging-config.js"],
                ELECTRON,
                "Electron Stage 50D Windows packaging 검증",
            ),
            "Stage 50C renderer UI 회귀검증": (
                [str(node), "tests/validate-renderer-ui.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Stage 50C 검색 service 회귀검증": (
                [str(node), "tests/validate-search-service.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Stage 50C 보안 골격 회귀검증": (
                [str(node), "tests/validate-electron-skeleton.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Stage 50C Python 전체 회귀검증": (
                [sys.executable, "50C_validate_kdrg_electron_renderer_ui.py"],
                ROOT,
                "PASS / 0 FAIL",
            ),
            "package-lock registry 독립검증": (
                [sys.executable, "scripts/validate-package-lock-registry.py"],
                ELECTRON,
                "package-lock registry canonicalization 검증",
            ),
            "checkout byte integrity 독립검증": (
                [sys.executable, "scripts/validate-checkout-byte-integrity.py"],
                ELECTRON,
                "checkout byte integrity 검증",
            ),
        }
        for name, (args, cwd, marker) in command_specs.items():
            result = run_command(args, cwd)
            outputs[name] = result
            check(
                name,
                result,
                f"returncode=0 and marker={marker}",
                lambda value, _expected, marker=marker: (
                    value["returncode"] == 0
                    and marker in value["stdout"]
                ),
            )

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    smoke_source = (ELECTRON / "src/packaged-runtime-smoke.js").read_text(encoding="utf-8")
    search_service_source = (ELECTRON / "src/kdrg-search-service.js").read_text(encoding="utf-8")
    relation_contract_source = (ELECTRON / "src/search-result-contract.js").read_text(encoding="utf-8")
    main_source = (ELECTRON / "main.js").read_text(encoding="utf-8")
    preload_source = (ELECTRON / "preload.js").read_text(encoding="utf-8")
    renderer_html = (ELECTRON / "renderer/index.html").read_text(encoding="utf-8")
    renderer_app = (ELECTRON / "renderer/app.js").read_text(encoding="utf-8")
    checkout_validator_source = (
        ELECTRON / "scripts/validate-checkout-byte-integrity.py"
    ).read_text(encoding="utf-8")
    parity_source = (
        ELECTRON / "tests/run-search-parity.js"
    ).read_text(encoding="utf-8")
    package_scripts = package.get("scripts", {})
    immutable_match = re.search(
        r"IMMUTABLE_DATA_HASHES\s*=\s*\{([\s\S]*?)\n\}",
        checkout_validator_source,
    )
    immutable_block = immutable_match.group(1) if immutable_match else ""
    check(
        "checkout 불변 SHA는 공식 데이터 3종만",
        immutable_match is not None
        and all(
            token in immutable_block
            for token in (
                "kdrg_v47_search_integrated_v3.json",
                "kdrg_v47_ui_semantic_profile.json",
                "kdrg_v47_ui_display_contract.json",
            )
        )
        and "renderer/index.html" not in immutable_block
        and "renderer/styles.css" not in immutable_block,
        True,
    )
    check(
        "checkout 변경형 UI는 EOL 전수검증",
        "OBSERVED_MUTABLE_TEXT_FILES" in checkout_validator_source
        and "electron/renderer/index.html" in checkout_validator_source
        and "electron/renderer/styles.css" in checkout_validator_source,
        True,
    )
    check(
        "parity 재귀 baseline subset 계약",
        "projectStatusByBaseline" in parity_source
        and "projectByBaseline" in parity_source
        and "additiveObjectKeys" in parity_source
        and "array length changed" in parity_source
        and "unexpected actual status transition value" in parity_source
        and "checkProjected" in parity_source,
        True,
    )
    check(
        "parity status 음성 self-test",
        "missing baseline key detected" in parity_source
        and "changed baseline value remains detectable" in parity_source,
        True,
    )
    check(
        "renderer CSS 단일 EOF LF",
        (ELECTRON / "renderer/styles.css").read_bytes().endswith(b"\n")
        and not (ELECTRON / "renderer/styles.css").read_bytes().endswith(b"\n\n"),
        True,
    )
    check(
        "변경형 UI 보호 SHA 비고정",
        all(relative not in PROTECTED_HASHES for relative in MUTABLE_UI_FILES),
        True,
    )
    check(
        "컴팩트 상단·결과·상세 UI 계약",
        'class="topbar compact-topbar"' in renderer_html
        and 'class="search-panel compact-search-panel"' in renderer_html
        and "result-card-main" in renderer_app
        and "detailSummaryLine" in renderer_app
        and "detail-overview-grid" in renderer_app,
        True,
    )
    check(
        "사용자 검색 유형 CODE·ADRG만",
        "SEARCH_ENTITY_TYPES = Object.freeze(['CODE', 'ADRG'])" in relation_contract_source
        and all(token in renderer_html for token in ('<option value="ALL">전체</option>', '<option value="CODE">코드</option>', '<option value="ADRG">ADRG</option>'))
        and all(token not in renderer_html for token in ('<option value="AADRG">', '<option value="RDRG">', '<option value="TABLE">')),
        True,
    )
    check(
        "TABLE 인라인 펼치기·기술 상세 분리",
        "async function loadInlineTable" in renderer_app
        and "create('details', `table-card inline-table-card" in renderer_app
        and "TABLE 기술 상세" in renderer_app
        and "TABLE을 펼치면 코드가 이 자리에서 표시됩니다." in renderer_app,
        True,
    )
    check(
        "TABLE 원문명 우선 표시",
        "OFFICIAL_TABLE_LABEL_PATTERN" in renderer_app
        and "원문 TABLE명 미수록" in renderer_app
        and "내부 ID ${tableId}" in renderer_app,
        True,
    )
    check(
        "AADRG 검색결과 분리 금지·파생정보 유지",
        "function renderTypeCounts(response)" in renderer_app
        and "for (const type of ['CODE', 'ADRG'])" in renderer_app
        and "function renderDerivedAadrgList" in renderer_app,
        True,
    )
    check(
        "packaged smoke 현재 results 계약 사용",
        "search.results" in smoke_source and "search.items.some" not in smoke_source,
        True,
    )
    check(
        "검색 service results 응답 계약 존재",
        "results," in search_service_source
        and "schema_version: RESPONSE_SCHEMA_VERSION" in search_service_source,
        True,
    )
    check(
        "관계검색 request 2~6개 계약",
        "payload.conditions.length < 2" in relation_contract_source
        and "payload.conditions.length > 6" in relation_contract_source,
        True,
    )
    check("관계검색 중복코드 차단", "같은 코드를 중복 입력할 수 없습니다" in relation_contract_source, True)
    check("관계검색 IPC 연결", "normalizeRelationRequest(payload)" in main_source and "kdrg:relation-search" in main_source, True)
    check("관계검색 preload bridge", "relationSearch: (request)" in preload_source, True)
    check("관계검색 service method", "relationSearch(conditions, operator = 'AND'" in search_service_source, True)
    check("관계검색 제외 TABLE 차단", "exclusionTableIds.has(tableId)" in search_service_source, True)
    check("관계검색 strict·split·partial", all(token in search_service_source for token in ("'strict'", "'split'", "'partial'")), True)
    check("관계검색 제외 TABLE 요약", "exclude_tables:" in search_service_source, True)
    check("packaged smoke 관계검색 fixture", "findRelationSmokeFixture(service)" in smoke_source, True)
    check("packaged smoke 관계검색 계약", "validateRelationResponse" in smoke_source and "relation_contract_verified" in smoke_source, True)
    check("데이터 현황 기본 접힘", bool(re.search(r'<details[^>]+id="data-overview"(?![^>]*\sopen)[^>]*>', renderer_html)), True)
    check("복수 코드 관계검색 UI", 'id="relation-search-panel"' in renderer_html and 'id="relation-form"' in renderer_html, True)
    check("기존 검색 필터 유지", all(token in renderer_html for token in ('id="filter-type"', 'id="filter-mdc"', 'id="filter-classification"')), True)
    check("상세 section 접기", "create('details', 'detail-section')" in renderer_app, True)
    check("TABLE 코드 기본 접힘", bool(re.search(r"makeSection\('TABLE 코드'[\s\S]{0,240}?open:\s*false", renderer_app)), True)
    check("상세 전체 펼치기·접기", "setAllDetailSections(true)" in renderer_app and "setAllDetailSections(false)" in renderer_app, True)
    check(
        "packaged smoke 계약검증 script",
        package_scripts.get("validate:smoke-contract"),
        "node tests/validate-packaged-runtime-smoke.js",
    )
    check(
        "전체 validate에 smoke 계약검증 포함",
        "validate:smoke-contract" in package_scripts.get("validate", ""),
        True,
    )
    check(
        "전체 check에 smoke 계약검증 문법 포함",
        "validate-packaged-runtime-smoke.js" in package_scripts.get("check", ""),
        True,
    )
    check(
        "packaged smoke 단계별 진단 포함",
        "completed_steps" in smoke_source and "failed_step" in smoke_source,
        True,
    )
    check(
        "dist:win script",
        package.get("scripts", {}).get("dist:win"),
        "electron-builder --win portable --x64 --publish never",
    )
    check("build asar", package.get("build", {}).get("asar"), True)
    check(
        "build portable target",
        package.get("build", {}).get("win", {}).get("target", [{}])[0].get("target"),
        "portable",
    )
    check(
        "extraResources 수",
        len(package.get("build", {}).get("extraResources", [])),
        3,
    )

    pyside_workflow = (
        ROOT / ".github/workflows/build-windows-release.yml"
    ).read_text(encoding="utf-8")
    check("PySide 태그 유지", '"v*.*.*"' in pyside_workflow, True)
    check("Electron 태그 분리", '"electron-v*"' in workflow_text, True)

    return write_report(checks, outputs)


if __name__ == "__main__":
    raise SystemExit(main())
